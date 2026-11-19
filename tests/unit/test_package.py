import re

import vlade_rag
from vlade_rag import native


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", vlade_rag.__version__)


def test_native_backend_is_consistent() -> None:
    if native.NATIVE_AVAILABLE:
        assert native.backend() == "rust"
        assert native.engine_version() is not None
    else:
        assert native.backend() == "python"
        assert native.engine_version() is None
