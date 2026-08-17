"""Guards the fork's ownership boundary.

src/platforms/ and src/nodriver_common.py are owned upstream: we never edit
them, we overwrite them wholesale from upstream. They reach into util.py, which
we *do* edit. That makes util.py a contract, not our property.

This test fails in both directions that matter:
  - we delete or rename something upstream calls
  - an upstream sync introduces a util.* reference we do not provide yet
"""

import ast

import pytest
from conftest import SRC

import util

UPSTREAM_OWNED = sorted((SRC / "platforms").glob("*.py")) + [SRC / "nodriver_common.py"]


def _util_attributes(path):
    """Every `util.X` in a file, via AST so strings and comments cannot match."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "util"
    }


def test_upstream_owned_files_exist():
    assert UPSTREAM_OWNED, "no upstream-owned files found - check the SRC path"
    for path in UPSTREAM_OWNED:
        assert path.is_file(), f"missing upstream-owned file: {path}"


@pytest.mark.parametrize("path", UPSTREAM_OWNED, ids=lambda p: p.name)
def test_util_contract_is_satisfied(path):
    missing = sorted(name for name in _util_attributes(path) if not hasattr(util, name))
    assert not missing, (
        f"{path.name} references util symbols that do not exist: {missing}. "
        "Either an edit to util.py broke the contract, or an upstream sync needs "
        "these symbols ported over."
    )


def test_contract_surface_is_reported():
    """Not an assertion on the exact number - just keeps the surface visible."""
    surface = set()
    for path in UPSTREAM_OWNED:
        surface |= _util_attributes(path)
    assert surface, "expected upstream files to depend on util"
    print(f"\nutil.py contract surface: {len(surface)} symbols")
