"""k-FP baseline features and the C1 ablation families."""

import numpy as np

from features.kfp import N_KFP, kfp_features
from scripts.evaluate_c1 import FAMILIES, _check_partition, family_columns


def test_kfp_counts_and_shape():
    t = np.arange(50) * 0.1
    d = np.where(np.arange(50) % 5 == 0, 1, -1)
    v = kfp_features(t, d)
    assert v.shape == (N_KFP,)
    assert v[:3].tolist() == [40, 10, 50]


def test_kfp_ignores_sizes_and_handles_empty():
    assert kfp_features([], []).shape == (N_KFP,)
    a = kfp_features([0.0, 0.5, 1.0], [1, -1, -1])
    b = kfp_features([1.0, 0.0, 0.5], [-1, 1, -1])      # same packets, unsorted
    assert np.allclose(a, b)


def test_ablation_families_partition_the_features():
    _check_partition()
    trace = np.concatenate([family_columns(f, False) for f in FAMILIES])
    role = np.concatenate([family_columns(f, True) for f in FAMILIES])
    assert sorted(trace.tolist()) == list(range(195))
    assert sorted(role.tolist()) == list(range(35))
