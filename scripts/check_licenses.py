"""Check runtime dependency licenses against the policy of ADR-0001.

Usage:
    pip-licenses --python <env-python> --from=mixed --format=json > licenses.json
    python scripts/check_licenses.py licenses.json

Exit code 0: every package uses an allowed license.
Exit code 1: at least one package is denied or unknown.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Permissive licenses accepted in the core install (ADR-0001, item 2).
ALLOWED_PATTERNS = [
    r"\bMIT\b",
    r"\bBSD\b",
    r"BSD-[23]-Clause",
    r"\bApache\b",
    r"Apache-2\.0",
    r"\bISC\b",
    r"\bPSF\b",
    r"Python Software Foundation",
    r"\bUnlicense\b",
    r"\bZlib\b",
    r"\bCC0\b",
]
# Accepted, but must be listed in ADR-0001 (item 3).
REVIEW_PATTERNS = [r"MPL-2\.0", r"Mozilla Public License 2\.0"]
# Never accepted in the core install (ADR-0001, item 4).
DENIED_PATTERNS = [
    r"GPL",  # also matches LGPL and AGPL
    r"General Public License",
    r"\bSSPL\b",
    r"Server Side Public License",
    r"\bBUSL\b",
    r"Business Source",
    r"\bRSAL\b",
    r"Source Available",
]

# Packages whose metadata does not state the license clearly. Each entry was checked by hand.
# Format: {"package-name": "license verified upstream"}.
REVIEWED_EXCEPTIONS: dict[str, str] = {}

# Workspace packages are MIT by definition.
IGNORED = {"vlade-rag", "vlade-rag-core"}


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def classify(license_text: str) -> str:
    """Return 'allowed', 'review', 'denied' or 'unknown'.

    An SPDX expression with OR passes when at least one alternative is allowed.
    An expression with AND fails when any part is denied.
    """
    alternatives = re.split(r"\s+OR\s+|;", license_text)
    results = []
    for alt in alternatives:
        if _matches(DENIED_PATTERNS, alt):
            results.append("denied")
        elif _matches(ALLOWED_PATTERNS, alt):
            results.append("allowed")
        elif _matches(REVIEW_PATTERNS, alt):
            results.append("review")
        else:
            results.append("unknown")
    for verdict in ("allowed", "review", "denied"):
        if verdict in results:
            return verdict
    return "unknown"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(__doc__ or "")
        return 2
    packages = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    failures = []
    for pkg in sorted(packages, key=lambda p: p["Name"].lower()):
        name, lic = pkg["Name"], pkg.get("License", "")
        if name.lower() in IGNORED:
            continue
        verdict = "allowed" if name.lower() in REVIEWED_EXCEPTIONS else classify(lic)
        print(f"{verdict:8} {name} {pkg.get('Version', '')}: {lic}")
        if verdict in ("denied", "unknown"):
            failures.append(f"{name}: {lic}")
        elif verdict == "review":
            print(f"         -> register {name} in docs/adr/0001-licenca-mit.md")
    if failures:
        print("\nLicense policy violations (ADR-0001):", *failures, sep="\n  ")
        return 1
    print(f"\nOK: {len(packages)} packages checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
