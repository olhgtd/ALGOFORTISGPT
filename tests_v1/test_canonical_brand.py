"""Permanent repository-wide canonical brand regression guard."""
from build.tools.check_canonical_brand import scan


def test_tracked_repository_uses_only_canonical_brand() -> None:
    findings = scan()
    assert findings == [], "retired product-name token found: " + ", ".join(f"{x.kind}:{x.path}" for x in findings)
