"""Models. Imported lazily: BurstTransformer needs torch, which the RF/GBT paths
(and a2a_leakcheck) do not."""

from importlib import import_module

_LAZY = {"RFClassifier": ".random_forest", "BurstTransformer": ".transformer"}

__all__ = list(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        return getattr(import_module(_LAZY[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
