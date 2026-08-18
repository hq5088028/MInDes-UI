from __future__ import annotations

from .zh_cn import STRINGS as BASE_STRINGS


def complete_catalog(overrides: dict[str, str]) -> dict[str, str]:
    """Return an independent catalog with the simplified-Chinese key contract."""
    unknown = set(overrides) - set(BASE_STRINGS)
    if unknown:
        raise KeyError(f"Unknown translation keys: {sorted(unknown)}")
    catalog = dict(BASE_STRINGS)
    catalog.update(overrides)
    return catalog
