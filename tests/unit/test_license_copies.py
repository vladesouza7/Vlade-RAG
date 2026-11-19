"""Package builds need a real LICENSE file inside each package directory.

Symlinks break the sdist, so each package keeps a copy. This test keeps the copies identical
to the repository LICENSE.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "copy", ["packages/python/LICENSE", "packages/rust/vlade_rag_core/LICENSE"]
)
def test_license_copy_matches_root(copy: str) -> None:
    path = ROOT / copy
    assert not path.is_symlink()
    assert path.read_bytes() == (ROOT / "LICENSE").read_bytes()
