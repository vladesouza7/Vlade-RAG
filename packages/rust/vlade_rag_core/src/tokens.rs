//! Approximate tokenizer. Specification: `vlade_rag.native._reference.token_spans`.
//! Offsets are code point indexes (Python string indexes), not byte offsets.

use crate::chars::{is_whitespace, is_word};

pub fn token_spans(text: &str) -> Vec<(usize, usize)> {
    let mut spans = Vec::new();
    let mut start: Option<usize> = None;
    let mut len = 0usize;
    for (i, c) in text.chars().enumerate() {
        len = i + 1;
        if is_word(c) {
            if start.is_none() {
                start = Some(i);
            }
            continue;
        }
        if let Some(s) = start.take() {
            spans.push((s, i));
        }
        if !is_whitespace(c) {
            spans.push((i, i + 1));
        }
    }
    if let Some(s) = start {
        spans.push((s, len));
    }
    spans
}

pub fn count_tokens(text: &str) -> usize {
    token_spans(text).len()
}

#[cfg(test)]
mod tests {
    use super::token_spans;

    #[test]
    fn words_and_punctuation() {
        assert_eq!(
            token_spans("Olá, mundo!"),
            vec![(0, 3), (3, 4), (5, 10), (10, 11)]
        );
    }

    #[test]
    fn empty() {
        assert!(token_spans("  \n ").is_empty());
    }
}
