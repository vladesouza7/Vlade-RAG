import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_licenses.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licenses", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _load()


@pytest.mark.parametrize(
    ("license_text", "verdict"),
    [
        ("MIT", "allowed"),
        ("MIT License", "allowed"),
        ("BSD-3-Clause", "allowed"),
        ("Apache-2.0", "allowed"),
        ("ISC License (ISCL)", "allowed"),
        ("PSF-2.0", "allowed"),
        ("MIT OR Apache-2.0", "allowed"),
        ("LGPL-3.0-only OR MIT", "allowed"),
        ("MPL-2.0", "review"),
        ("LGPL-3.0-only", "denied"),
        ("GNU Affero General Public License v3", "denied"),
        ("AGPL-3.0", "denied"),
        ("SSPL-1.0", "denied"),
        ("UNKNOWN", "unknown"),
        ("", "unknown"),
    ],
)
def test_classify(license_text: str, verdict: str) -> None:
    assert check.classify(license_text) == verdict
