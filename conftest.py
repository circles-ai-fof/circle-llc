"""
conftest.py — root pytest configuration for circle-llc monorepo.

Adds outcome-db/ to sys.path as the "outcome_db" package namespace
so tests can do `from outcome_db.write_gate import ...`.
The hyphenated directory name (outcome-db) is not directly importable;
we use a path hook to bridge the naming gap.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).parent


class _HyphenPackageFinder(importlib.abc.MetaPathFinder):
    """Maps `outcome_db` imports to the `outcome-db/` directory."""

    _MAP: dict[str, Path] = {
        "outcome_db": REPO_ROOT / "outcome-db",
    }

    def find_spec(
        self,
        fullname: str,
        path: object,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        # Top-level package
        root_name = fullname.split(".")[0]
        if root_name not in self._MAP:
            return None

        base_dir = self._MAP[root_name]

        if fullname == root_name:
            # Package itself
            init = base_dir / "__init__.py"
            origin = str(init) if init.exists() else None
            spec = importlib.machinery.ModuleSpec(
                name=fullname,
                loader=importlib.machinery.SourceFileLoader(fullname, origin) if origin else None,
                origin=origin,
                is_package=True,
            )
            spec.submodule_search_locations = [str(base_dir)]
            return spec

        # Submodule: outcome_db.write_gate → outcome-db/write_gate.py
        submodule = fullname[len(root_name) + 1:]  # strip "outcome_db."
        module_file = base_dir / (submodule.replace(".", os.sep) + ".py")
        if module_file.exists():
            loader = importlib.machinery.SourceFileLoader(fullname, str(module_file))
            spec = importlib.machinery.ModuleSpec(
                name=fullname,
                loader=loader,
                origin=str(module_file),
            )
            return spec

        return None


# Register the finder once
if not any(isinstance(f, _HyphenPackageFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _HyphenPackageFinder())
