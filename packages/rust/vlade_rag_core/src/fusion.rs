//! Reciprocal Rank Fusion. Specification: `vlade_rag.native._reference.rrf_fuse`.

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};

const MISSING: usize = 1 << 62;

pub fn rrf_fuse(
    rankings: &[Vec<String>],
    k: f64,
    weights: Option<&[f64]>,
    top_k: usize,
) -> Result<Vec<(String, f64)>, String> {
    if let Some(w) = weights {
        if w.len() != rankings.len() {
            return Err("weights must have one value per ranking".into());
        }
    }
    if k <= 0.0 {
        return Err("k must be positive".into());
    }
    let mut order: Vec<String> = Vec::new();
    let mut scores: HashMap<String, f64> = HashMap::new();
    let mut ranks: HashMap<String, Vec<usize>> = HashMap::new();
    for (i, ranking) in rankings.iter().enumerate() {
        let w = weights.map_or(1.0, |w| w[i]);
        let mut seen: HashSet<&str> = HashSet::new();
        for (position0, item) in ranking.iter().enumerate() {
            if !seen.insert(item.as_str()) {
                continue;
            }
            let position = position0 + 1;
            if !scores.contains_key(item) {
                scores.insert(item.clone(), 0.0);
                ranks.insert(item.clone(), vec![MISSING; rankings.len()]);
                order.push(item.clone());
            }
            *scores.get_mut(item).expect("present") += w / (k + position as f64);
            ranks.get_mut(item).expect("present")[i] = position;
        }
    }
    order.sort_by(|a, b| {
        scores[b]
            .partial_cmp(&scores[a])
            .unwrap_or(Ordering::Equal)
            .then_with(|| ranks[a].cmp(&ranks[b]))
            .then_with(|| a.cmp(b))
    });
    Ok(order
        .into_iter()
        .take(top_k)
        .map(|d| {
            let s = scores[&d];
            (d, s)
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::rrf_fuse;

    fn v(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| (*s).to_string()).collect()
    }

    #[test]
    fn fuses_two_lists() {
        let out = rrf_fuse(&[v(&["a", "b"]), v(&["b", "c"])], 60.0, None, 10).unwrap();
        let ids: Vec<&str> = out.iter().map(|(d, _)| d.as_str()).collect();
        assert_eq!(ids, vec!["b", "a", "c"]);
    }

    #[test]
    fn rejects_bad_weights() {
        assert!(rrf_fuse(&[v(&["a"])], 60.0, Some(&[1.0, 2.0]), 10).is_err());
    }
}
