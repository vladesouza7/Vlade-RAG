//! PyO3 bindings. The Python module name is `vlade_rag_core`.

use pyo3::prelude::*;

#[pymodule]
fn vlade_rag_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", crate::VERSION)?;
    Ok(())
}
