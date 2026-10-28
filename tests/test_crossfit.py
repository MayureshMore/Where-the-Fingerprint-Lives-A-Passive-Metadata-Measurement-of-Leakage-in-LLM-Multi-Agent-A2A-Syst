"""Cross-fitted transfer never trains on a test fold's prompts."""

import numpy as np
from sklearn.neighbors import KNeighborsClassifier

from evaluation.crossfit import crossfit_predict, shared_prompt_fraction


class _Spy:
    """1-NN that records the groups it was trained on."""

    seen: list = []

    def __init__(self):
        self.clf = KNeighborsClassifier(1)

    def fit(self, X, y):
        _Spy.seen.append(set(X[:, 1].astype(int)))
        self.clf.fit(X, y)
        return self

    def predict(self, X):
        return self.clf.predict(X)


def _data(seed):
    # label is random per prompt; feature 0 is a prompt fingerprint, feature 1 the group id
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(40), 3)
    labels = np.array(["a", "b"])[np.random.default_rng(0).integers(0, 2, 40)][groups]
    X = np.column_stack([groups * 10.0 + rng.normal(0, 0.1, len(groups)), groups])
    return X, labels, groups.astype(str)


def test_crossfit_excludes_test_prompts_and_kills_prompt_matching():
    Xs, ys, gs = _data(1)
    Xt, yt, gt = _data(2)
    assert shared_prompt_fraction(gs, gt) == 1.0
    full = _Spy().fit(Xs, ys).predict(Xt)
    assert (full == yt).mean() == 1.0                     # prompt matching alone is perfect
    _Spy.seen = []
    pred = crossfit_predict(_Spy, Xs, ys, gs, Xt, yt, gt)
    for trained, (_, te) in zip(_Spy.seen, _fold_groups(yt, gt)):
        assert not trained & te
    assert (pred == yt).mean() < 0.8


def _fold_groups(yt, gt):
    from evaluation.crossfit import _folds
    for tr, te in _folds(np.asarray(yt), np.asarray(gt), 5):
        yield tr, set(np.asarray(gt)[te].astype(int))
