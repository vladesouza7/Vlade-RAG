//! Chunking. Specification: `vlade_rag.native._reference.split_text`.

use crate::tokens::token_spans;

const HEADING_SCORE: u8 = 5;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Strategy {
    Tokens,
    Recursive,
    Markdown,
    Sentence,
}

impl Strategy {
    pub fn parse(name: &str) -> Option<Self> {
        match name {
            "tokens" => Some(Self::Tokens),
            "recursive" => Some(Self::Recursive),
            "markdown" => Some(Self::Markdown),
            "sentence" => Some(Self::Sentence),
            _ => None,
        }
    }
}

fn is_sentence_end(token: &[char]) -> bool {
    token.len() == 1 && matches!(token[0], '.' | '!' | '?' | '…')
}

fn boundary_scores(chars: &[char], spans: &[(usize, usize)], strategy: Strategy) -> Vec<u8> {
    let mut scores = vec![0u8; spans.len()];
    for i in 1..spans.len() {
        if strategy == Strategy::Tokens {
            scores[i] = 1;
            continue;
        }
        let gap = &chars[spans[i - 1].1..spans[i].0];
        let newlines = gap.iter().filter(|c| **c == '\n').count();
        let prev = &chars[spans[i - 1].0..spans[i - 1].1];
        let sentence_end = is_sentence_end(prev) && !gap.is_empty();
        if strategy == Strategy::Sentence {
            scores[i] = if newlines >= 1 || sentence_end {
                2
            } else if !gap.is_empty() {
                1
            } else {
                0
            };
            continue;
        }
        let mut base = if newlines >= 2 {
            4
        } else if newlines == 1 {
            3
        } else if sentence_end {
            2
        } else if !gap.is_empty() {
            1
        } else {
            0
        };
        if strategy == Strategy::Markdown && newlines >= 1 && chars[spans[i].0] == '#' {
            base = HEADING_SCORE;
        }
        scores[i] = base;
    }
    scores
}

/// Returns `(start, end, token_count)` per chunk. Offsets are code point indexes.
pub fn split_text(
    text: &str,
    strategy: Strategy,
    max_tokens: usize,
    overlap_tokens: usize,
) -> Vec<(usize, usize, usize)> {
    assert!(max_tokens >= 1, "max_tokens must be at least 1");
    let overlap = overlap_tokens.min(max_tokens - 1);
    let chars: Vec<char> = text.chars().collect();
    let spans = token_spans(text);
    let n = spans.len();
    if n == 0 {
        return Vec::new();
    }
    let scores = boundary_scores(&chars, &spans, strategy);
    let min_size = (max_tokens / 4).max(1);
    let mut chunks = Vec::new();
    let mut s = 0usize;
    while s < n {
        let e = (s + max_tokens).min(n);
        let cut = if e == n {
            n
        } else {
            let mut cut = e;
            let mut best: i16 = -1;
            for (c, score) in scores.iter().enumerate().take(e + 1).skip(s + min_size) {
                if i16::from(*score) >= best {
                    best = i16::from(*score);
                    cut = c;
                }
            }
            cut
        };
        chunks.push((spans[s].0, spans[cut - 1].1, cut - s));
        if cut >= n {
            break;
        }
        // No overlap across a Markdown heading: the next chunk starts at the heading.
        s = if scores[cut] == HEADING_SCORE {
            cut
        } else {
            cut.saturating_sub(overlap).max(s + 1)
        };
    }
    chunks
}

#[cfg(test)]
mod tests {
    use super::{Strategy, split_text};

    #[test]
    fn single_chunk_when_text_fits() {
        assert_eq!(
            split_text("a b c", Strategy::Tokens, 10, 0),
            vec![(0, 5, 3)]
        );
    }

    #[test]
    fn prefers_paragraph_breaks() {
        let text = "a b c.\n\nd e f g h";
        let chunks = split_text(text, Strategy::Recursive, 6, 0);
        assert_eq!(chunks[0], (0, 6, 4));
    }

    #[test]
    fn markdown_cuts_before_heading() {
        let text = "intro text here\n# Title\nbody body body body";
        let chunks = split_text(text, Strategy::Markdown, 8, 0);
        assert_eq!(&text[chunks[1].0..chunks[1].0 + 1], "#");
    }
}
