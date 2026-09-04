"""Stable ``api:app`` compatibility entry point."""

import importlib as _importlib
import importlib.util as _importlib_util
from pathlib import Path as _Path
import sys as _sys
import types as _types


_already_loaded = globals().get("_API_COMPATIBILITY_LOADED", False)
if __name__ == "api":
    _runtime = _importlib.import_module("api_runtime")
    if _already_loaded:
        _runtime = _importlib.reload(_runtime)
else:
    _runtime_name = f"{__name__}_runtime"
    _runtime_spec = _importlib_util.spec_from_file_location(
        _runtime_name,
        _Path(__file__).with_name("api_runtime.py"),
    )
    if _runtime_spec is None or _runtime_spec.loader is None:
        raise ImportError("Unable to load the isolated API runtime.")
    _runtime = _importlib_util.module_from_spec(_runtime_spec)
    _sys.modules[_runtime_name] = _runtime
    _runtime_spec.loader.exec_module(_runtime)


class _ApiCompatibilityModule(_types.ModuleType):
    """Forward historical reads and writes to the authoritative API runtime."""

    def __getattr__(self, name):
        return getattr(_runtime, name)

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(dir(_runtime)))

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return super().__setattr__(name, value)
        setattr(_runtime, name, value)


_module = _sys.modules[__name__]
_module.__class__ = _ApiCompatibilityModule
_API_COMPATIBILITY_LOADED = True
