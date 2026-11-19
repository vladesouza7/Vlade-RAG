//! Content hash and SimHash. Specification: `vlade_rag.native._reference`.

use sha2::{Digest, Sha256};

use crate::chars::is_word;
use crate::tokens::token_spans;

const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

pub fn content_hash(data: &[u8]) -> String {
    let digest = Sha256::digest(data);
    let mut out = String::with_capacity(64);
    for byte in digest.iter() {
        out.push_str(&format!("{byte:02x}"));
    }
    out
}

fn fnv1a64(data: &[u8]) -> u64 {
    let mut h = FNV_OFFSET;
    for b in data {
        h ^= u64::from(*b);
        h = h.wrapping_mul(FNV_PRIME);
    }
    h
}

pub fn simhash(text: &str) -> u64 {
    let chars: Vec<char> = text.chars().collect();
    let mut weights = [0i64; 64];
    let mut found = false;
    for (start, end) in token_spans(text) {
        if !is_word(chars[start]) {
            continue;
        }
        found = true;
        let token: String = chars[start..end].iter().collect::<String>().to_lowercase();
        let h = fnv1a64(token.as_bytes());
        for (bit, weight) in weights.iter_mut().enumerate() {
            *weight += if (h >> bit) & 1 == 1 { 1 } else { -1 };
        }
    }
    if !found {
        return 0;
    }
    let mut value = 0u64;
    for (bit, weight) in weights.iter().enumerate() {
        if *weight > 0 {
            value |= 1 << bit;
        }
    }
    value
}

#[cfg(test)]
mod tests {
    use super::{content_hash, simhash};

    #[test]
    fn sha256_of_empty() {
        assert_eq!(
            content_hash(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn simhash_is_case_insensitive() {
        assert_eq!(simhash("Olá Mundo"), simhash("olá mundo"));
        assert_eq!(simhash("..."), 0);
    }
}
