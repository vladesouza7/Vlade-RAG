//! Character classes shared by all functions. Must match `_reference.py`.

pub fn is_space_like(c: char) -> bool {
    matches!(
        c,
        '\t' | '\u{00a0}' | '\u{1680}' | '\u{2000}'
            ..='\u{200a}' | '\u{202f}' | '\u{205f}' | '\u{3000}'
    )
}

pub fn is_dropped_format(c: char) -> bool {
    matches!(
        c,
        '\u{00ad}' | '\u{200b}'..='\u{200f}' | '\u{2060}' | '\u{feff}'
    )
}

pub fn is_control(c: char) -> bool {
    let cp = c as u32;
    cp < 0x20 || (0x7f..=0x9f).contains(&cp)
}

pub fn is_whitespace(c: char) -> bool {
    matches!(
        c,
        ' ' | '\n' | '\r' | '\u{0b}' | '\u{0c}' | '\u{85}' | '\u{2028}' | '\u{2029}'
    ) || is_space_like(c)
}

pub fn is_word(c: char) -> bool {
    c.is_alphanumeric()
}
