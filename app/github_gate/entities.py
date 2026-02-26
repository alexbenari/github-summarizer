from __future__ import annotations

ALL_ENTITIES: tuple[str, ...] = (
    "metadata",
    "languages",
    "tree",
    "readme",
    "documentation",
    "build_package",
    "tests",
    "code",
)

ALL_ENTITIES_SET: frozenset[str] = frozenset(ALL_ENTITIES)

