//! PyO3 bindings. The Python module name is `vlade_rag_core`.
//! Each function copies its input and releases the GIL while it runs.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::{chunking, fusion, hashing, normalize, tokens};

#[pyfunction]
#[pyo3(signature = (text, dehyphenate = true))]
fn normalize_text(py: Python<'_>, text: &str, dehyphenate: bool) -> String {
    let text = text.to_owned();
    py.detach(move || normalize::normalize_text(&text, dehyphenate))
}

#[pyfunction]
fn token_spans(py: Python<'_>, text: &str) -> Vec<(usize, usize)> {
    let text = text.to_owned();
    py.detach(move || tokens::token_spans(&text))
}

#[pyfunction]
fn count_tokens(py: Python<'_>, texts: Vec<String>) -> Vec<usize> {
    py.detach(move || texts.iter().map(|t| tokens::count_tokens(t)).collect())
}

#[pyfunction]
fn split_text(
    py: Python<'_>,
    text: &str,
    strategy: &str,
    max_tokens: usize,
    overlap_tokens: usize,
) -> PyResult<Vec<(usize, usize, usize)>> {
    let strategy = chunking::Strategy::parse(strategy)
        .ok_or_else(|| PyValueError::new_err(format!("unknown strategy '{strategy}'")))?;
    if max_tokens < 1 {
        return Err(PyValueError::new_err("max_tokens must be at least 1"));
    }
    let text = text.to_owned();
    Ok(py.detach(move || chunking::split_text(&text, strategy, max_tokens, overlap_tokens)))
}

#[pyfunction]
fn content_hash(py: Python<'_>, data: Vec<u8>) -> String {
    py.detach(move || hashing::content_hash(&data))
}

#[pyfunction]
fn simhash(py: Python<'_>, text: &str) -> u64 {
    let text = text.to_owned();
    py.detach(move || hashing::simhash(&text))
}

#[pyfunction]
#[pyo3(signature = (rankings, k = 60.0, weights = None, top_k = 10))]
fn rrf_fuse(
    py: Python<'_>,
    rankings: Vec<Vec<String>>,
    k: f64,
    weights: Option<Vec<f64>>,
    top_k: usize,
) -> PyResult<Vec<(String, f64)>> {
    py.detach(move || fusion::rrf_fuse(&rankings, k, weights.as_deref(), top_k))
        .map_err(PyValueError::new_err)
}

#[pymodule]
fn vlade_rag_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", crate::VERSION)?;
    m.add_function(wrap_pyfunction!(normalize_text, m)?)?;
    m.add_function(wrap_pyfunction!(token_spans, m)?)?;
    m.add_function(wrap_pyfunction!(count_tokens, m)?)?;
    m.add_function(wrap_pyfunction!(split_text, m)?)?;
    m.add_function(wrap_pyfunction!(content_hash, m)?)?;
    m.add_function(wrap_pyfunction!(simhash, m)?)?;
    m.add_function(wrap_pyfunction!(rrf_fuse, m)?)?;
    Ok(())
}
