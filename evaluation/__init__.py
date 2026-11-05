"""Evaluation drivers. Imported lazily, so that evaluation.stats alone (a2a_leakcheck) does not
load the drivers' dependencies."""

from importlib import import_module

_LAZY = {"TopologyMetrics": ".metrics", "classification_metrics": ".metrics",
         "ClosedWorldEval": ".closed_world", "OpenWorldEval": ".open_world"}

__all__ = list(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        return getattr(import_module(_LAZY[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
