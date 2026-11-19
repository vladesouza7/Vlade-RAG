//! Vlade-RAG native engine.
//!
//! Rules (ADR-0003):
//! - Only pure, deterministic, CPU-bound work lives here.
//! - No network, database or filesystem access. Python passes data in and receives data back.
//! - Every exported function has a pure-Python reference implementation in `vlade_rag.native`.

/// Version of the native engine, taken from `Cargo.toml`.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

#[cfg(feature = "python")]
mod python;

#[cfg(test)]
mod tests {
    use super::VERSION;

    #[test]
    fn version_is_semver() {
        let parts: Vec<&str> = VERSION.split('.').collect();
        assert_eq!(parts.len(), 3);
        assert!(parts.iter().all(|p| p.parse::<u32>().is_ok()));
    }
}
