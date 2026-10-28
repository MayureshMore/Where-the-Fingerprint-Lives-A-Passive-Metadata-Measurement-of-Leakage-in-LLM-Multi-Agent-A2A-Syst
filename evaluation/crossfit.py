"""
Prompt-disjoint (cross-fitted) transfer between two collections.

Collections drawn from the same prompt generators share prompts, and a request's
size is fixed by its prompt, so a model trained on all of one collection and
tested on another can match prompt-specific sizes instead of learning the
behaviour. Cross-fitting removes that: split the TARGET into group folds by
prompt_group, and predict each fold with a model trained only on SOURCE traces
whose prompt group does not occur in that fold.

Dropping the shared groups also shrinks the training set, so `size_matched`
drops the same number of source groups chosen at random from those NOT in the
fold. full → size_matched isolates the training-size effect; size_matched →
crossfit isolates the shared-prompt effect.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

SEED = 42


def _folds(y_te, g_te, n_splits: int):
    classes = sorted(set(y_te))
    groups_per_class = min(len(set(g_te[y_te == c])) for c in classes)
    k = max(2, min(n_splits, groups_per_class))
    return StratifiedGroupKFold(k, shuffle=True, random_state=SEED).split(np.zeros(len(y_te)), y_te, g_te)


def crossfit_predict(make_clf: Callable, X_tr, y_tr, g_tr, X_te, y_te, g_te,
                     n_splits: int = 5, size_matched: bool = False) -> np.ndarray:
    """Out-of-fold predictions for the target, never training on a test fold's prompts.

    size_matched=True instead drops an equal number of randomly chosen source groups that
    are NOT in the test fold (the training-size control)."""
    y_tr, g_tr, y_te, g_te = (np.asarray(v) for v in (y_tr, g_tr, y_te, g_te))
    rng = np.random.default_rng(SEED)
    pred = np.empty(len(y_te), dtype=object)
    for _, te in _folds(y_te, g_te, n_splits):
        test_groups = np.unique(g_te[te])
        shared = np.isin(g_tr, test_groups)
        if size_matched:
            n_drop = len(np.intersect1d(np.unique(g_tr), test_groups))
            pool = np.setdiff1d(np.unique(g_tr), test_groups)
            dropped = rng.choice(pool, size=min(n_drop, len(pool)), replace=False)
            keep = ~np.isin(g_tr, dropped)
        else:
            keep = ~shared
        pred[te] = make_clf().fit(X_tr[keep], list(y_tr[keep])).predict(X_te[te])
    return pred


def shared_prompt_fraction(g_tr, g_te) -> float:
    """Fraction of target traces whose prompt also occurs in the source."""
    g_te = np.asarray(g_te)
    return float(np.isin(g_te, np.unique(np.asarray(g_tr))).mean()) if len(g_te) else 0.0
