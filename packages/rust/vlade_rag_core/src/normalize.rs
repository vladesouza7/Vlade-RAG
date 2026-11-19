//! Text normalization. Specification: `vlade_rag.native._reference.normalize_text`.

use unicode_normalization::UnicodeNormalization;

use crate::chars::{is_control, is_dropped_format, is_space_like, is_word};

pub fn normalize_text(text: &str, dehyphenate: bool) -> String {
    let nfc: String = text.nfc().collect();
    let replaced = nfc.replace("\r\n", "\n").replace('\r', "\n");

    let mut cleaned: Vec<char> = Vec::with_capacity(replaced.len());
    for c in replaced.chars() {
        if c == '\n' {
            cleaned.push(c);
        } else if is_space_like(c) {
            cleaned.push(' ');
        } else if is_control(c) || is_dropped_format(c) {
            continue;
        } else {
            cleaned.push(c);
        }
    }
    if dehyphenate {
        cleaned = dehyphenate_chars(&cleaned);
    }

    let collected: String = cleaned.into_iter().collect();
    let joined = collected
        .split('\n')
        .map(|line| {
            line.split(' ')
                .filter(|part| !part.is_empty())
                .collect::<Vec<_>>()
                .join(" ")
        })
        .collect::<Vec<_>>()
        .join("\n");

    let mut out = String::with_capacity(joined.len());
    let mut newlines = 0usize;
    for c in joined.chars() {
        if c == '\n' {
            newlines += 1;
            if newlines <= 2 {
                out.push(c);
            }
        } else {
            newlines = 0;
            out.push(c);
        }
    }
    out.trim_matches(|c| c == '\n' || c == ' ').to_string()
}

fn dehyphenate_chars(chars: &[char]) -> Vec<char> {
    let n = chars.len();
    let mut out = Vec::with_capacity(n);
    let mut i = 0;
    while i < n {
        if chars[i] == '-'
            && i > 0
            && i + 2 < n
            && chars[i + 1] == '\n'
            && is_word(chars[i - 1])
            && is_word(chars[i + 2])
        {
            i += 2;
            continue;
        }
        out.push(chars[i]);
        i += 1;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::normalize_text;

    #[test]
    fn collapses_and_strips() {
        assert_eq!(normalize_text("  a  b \r\n\r\n\r\n c\t", true), "a b\n\nc");
    }

    #[test]
    fn dehyphenates_words() {
        assert_eq!(normalize_text("infor-\nmação", true), "informação");
        assert_eq!(normalize_text("infor-\nmação", false), "infor-\nmação");
    }

    #[test]
    fn removes_format_characters() {
        assert_eq!(normalize_text("a\u{00ad}b\u{200b}c\u{feff}", true), "abc");
    }
}
