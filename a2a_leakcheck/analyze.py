"""
Analysis, detection, validation and prioritization for one attribute.

analysis        out-of-fold predictions from StratifiedGroupKFold (groups never split), macro-F1
                with a 95% cluster-bootstrap CI over groups
detection       chance = 1/k classes; with m = margin:
                    LEAK          CI lower bound >  chance + m
                    NO LEAK       CI upper bound <= chance + m
                    INCONCLUSIVE  otherwise
validation      minimum-sample check (every class needs min_per_class samples in at least
                n_splits groups; else INCONCLUSIVE without analysis), and a label-permutation
                test: the same CV on R label permutations (default 99, so p can reach 0.01). The
                test uses its own model (null_model, default a light random forest): it scores
                the real labels and every permutation with that model, so the p-value
                (1 + #null ≥ observed) / (R + 1) is exact for it; a weaker null model can only
                make the test more conservative. A LEAK whose p-value exceeds alpha becomes
                INCONCLUSIVE, and so does a NO LEAK the test contradicts (p <= alpha). Each
                permuted run also gets a verdict, and the share of them that read LEAK is the
                tool's false-positive rate on that data.
model           GBT as in the repository (models/gradient_boosted.py), with the leaf size lowered
                on training folds under 2 × 20 samples per class (gbt_min_leaf), where 20 per
                leaf would allow no split
prioritization  effect size = (macro-F1 − chance) / (1 − chance), the share of the way from
                chance to perfect; severity high / medium / low by the thresholds in rules.yaml
attribution     the same CV on each feature family alone (sizes, timing, counts and direction)
                and on one request-size feature alone, each paired against all features
"""

from __future__ import annotations

from dataclasses import dataclass

import os

import numpy as np
from joblib import Parallel, delayed, parallel_config
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold

from evaluation.stats import bootstrap_ci, paired_bootstrap_diff
from models.gradient_boosted import GBTClassifier
from models.random_forest import RFClassifier

LEAK, NO_LEAK, INCONCLUSIVE = "LEAK", "NO LEAK", "INCONCLUSIVE"


@dataclass
class Config:
    margin: float = 0.05
    n_splits: int = 5
    n_boot: int = 1000
    permutations: int = 99
    alpha: float = 0.05
    min_per_class: int = 20
    seed: int = 42
    model: str = "gbt"
    null_model: str = "rf-light"       # model of the permutation test; "same" = model
    jobs: int = -1                     # parallel CV runs (-1: one per core)


def verdict(ci_lo: float, ci_hi: float, chance: float, margin: float) -> str:
    if ci_lo > chance + margin:
        return LEAK
    if ci_hi <= chance + margin:
        return NO_LEAK
    return INCONCLUSIVE


def severity(effect: float, thresholds: dict) -> str:
    if effect >= thresholds.get("high", 0.6):
        return "high"
    if effect >= thresholds.get("medium", 0.3):
        return "medium"
    return "low"


MODELS = ("gbt", "rf", "rf-light")


GBT_MIN_LEAF = 20                  # the repository's GBT (models/gradient_boosted.py)


def gbt_min_leaf(n_train: int, n_classes: int) -> int:
    """GBT leaf size for a training fold: the repository's 20, lowered on small folds so that a
    split is possible at all. With 20 per leaf a fold under 40 samples cannot split, the model
    predicts one class, and its chance-level score would read as NO LEAK. Folds with at least
    2 × 20 samples per class keep 20."""
    return max(1, min(GBT_MIN_LEAF, n_train // (2 * max(n_classes, 1))))


def _model(name: str, seed: int = 42, n_train: int | None = None, n_classes: int | None = None):
    if name == "gbt":
        m = clone(GBTClassifier().pipeline)
        if n_train is not None:
            m.set_params(gbt__min_samples_leaf=gbt_min_leaf(n_train, n_classes or 2))
        return m
    if name == "rf":
        return clone(RFClassifier().pipeline)
    if name == "rf-light":
        return RandomForestClassifier(n_estimators=100, max_depth=12, class_weight="balanced",
                                      n_jobs=1, random_state=seed)
    raise ValueError(f"unknown model {name!r} ({', '.join(MODELS)})")


def _splits(y, g, cfg: Config):
    return list(StratifiedGroupKFold(cfg.n_splits, shuffle=True, random_state=cfg.seed)
                .split(np.zeros(len(y)), y, g))


def _oof(X, y, splits, cfg: Config, model: str | None = None) -> np.ndarray:
    pred = np.empty(len(y), dtype=object)
    for tr, te in splits:
        m = _model(model or cfg.model, cfg.seed, len(tr), len(np.unique(y[tr])))
        pred[te] = m.fit(X[tr], y[tr]).predict(X[te])
    return pred


def _null_run(X, y, g, classes, cfg: Config, model: str) -> tuple[float, str]:
    """One permuted-label run: the CV on its own folds, scored and given a verdict."""
    sp = _score(y, _oof(X, y, _splits(y, g, cfg), cfg, model), g, classes, cfg)
    return sp["macro_f1"], verdict(sp["ci_lo"], sp["ci_hi"], 1.0 / len(classes), cfg.margin)


def _parallel(calls: list, jobs: int) -> list:
    """Run independent CVs in worker processes, capping each worker's own threads (GBT and
    numpy use OpenMP/BLAS threads) so the workers do not oversubscribe the cores."""
    n = os.cpu_count() or 1
    workers = n if jobs in (-1, 0) else max(1, jobs)
    with parallel_config(backend="loky", inner_max_num_threads=max(1, n // min(workers, max(len(calls), 1)))):
        return Parallel(n_jobs=workers)(delayed(f)(*args) for f, *args in calls)


def _score(y, pred, g, classes, cfg: Config) -> dict:
    ci = bootstrap_ci(list(y), list(pred), classes=classes, groups=list(g), n=cfg.n_boot, seed=cfg.seed)
    return {"macro_f1": ci["macro_f1"], "ci_lo": ci["macro_f1_ci_lo"], "ci_hi": ci["macro_f1_ci_hi"],
            "accuracy": ci["accuracy"]}


def sample_check(y, g, cfg: Config) -> dict:
    classes, counts = np.unique(y, return_counts=True)
    groups = {str(c): int(len(np.unique(g[y == c]))) for c in classes}
    problems = []
    if len(classes) < 2:
        problems.append(f"only {len(classes)} class")
    problems += [f"{c}: {n} samples < {cfg.min_per_class}" for c, n in zip(classes, counts)
                 if n < cfg.min_per_class]
    problems += [f"{c}: {n} groups < {cfg.n_splits} folds" for c, n in groups.items() if n < cfg.n_splits]
    return {"ok": not problems, "problems": problems, "min_per_class": cfg.min_per_class,
            "per_class": {str(c): int(n) for c, n in zip(classes, counts)}, "groups_per_class": groups}


def analyze(X: np.ndarray, y: np.ndarray, g: np.ndarray, families: dict[str, np.ndarray],
            single: tuple[str, np.ndarray] | None, cfg: Config, severity_thresholds: dict) -> dict:
    """Everything the report needs for one attribute. single = (name, one request-size column).
    With no families and no single feature there is no attribution; the verdict does not use it."""
    y, g = np.asarray(y).astype(str), np.asarray(g).astype(str)
    classes = sorted(set(y.tolist()))
    chance = 1.0 / max(len(classes), 1)
    out = {"classes": classes, "n": int(len(y)), "n_groups": int(len(np.unique(g))), "chance": chance,
           "margin": cfg.margin, "threshold": chance + cfg.margin}
    check = sample_check(y, g, cfg)
    out["validation"] = {"min_samples": check}
    if not check["ok"]:
        out.update({"verdict": INCONCLUSIVE, "reason": "too few samples: " + "; ".join(check["problems"]),
                    "analysis": None, "prioritization": {"effect_size": None, "severity": "none"},
                    "attribution": None})
        return out

    splits = _splits(y, g, cfg)
    null_model = cfg.model if cfg.null_model == "same" else cfg.null_model
    rng = np.random.default_rng(cfg.seed)
    perms = [rng.permutation(y) for _ in range(cfg.permutations)]
    # every CV of this attribute in one pool: the model on all features, on each family, on the
    # single request-size feature, the null model on the real labels, and the permutations
    fam_cols = list(families.items())
    calls = [(_oof, X, y, splits, cfg)]
    calls += [(_oof, X[:, cols], y, splits, cfg) for _, cols in fam_cols]
    if single is not None:
        calls.append((_oof, single[1].reshape(-1, 1), y, splits, cfg))
    if cfg.permutations and null_model != cfg.model:
        calls.append((_oof, X, y, splits, cfg, null_model))
    n_fixed = len(calls)
    calls += [(_null_run, X, yp, g, classes, cfg, null_model) for yp in perms]
    done = _parallel(calls, cfg.jobs)
    pred, fam_preds = done[0], done[1:1 + len(fam_cols)]
    single_pred = done[1 + len(fam_cols)] if single is not None else None
    null_obs_pred = done[n_fixed - 1] if cfg.permutations and null_model != cfg.model else None
    null_runs = done[n_fixed:]

    s = _score(y, pred, g, classes, cfg)
    v = verdict(s["ci_lo"], s["ci_hi"], chance, cfg.margin)
    out["analysis"] = {**s, "model": cfg.model, "folds": cfg.n_splits}

    perm = {"permutations": cfg.permutations, "alpha": cfg.alpha, "null_model": null_model}
    if cfg.permutations:
        observed = s["macro_f1"] if null_obs_pred is None else \
            float(f1_score(y, null_obs_pred, labels=classes, average="macro", zero_division=0))
        null_f1 = [f for f, _ in null_runs]
        null_verdicts = [nv for _, nv in null_runs]
        p_value = (1 + sum(f >= observed for f in null_f1)) / (cfg.permutations + 1)
        perm.update({"observed_macro_f1": observed, "p_value": p_value,
                     "null_mean": float(np.mean(null_f1)), "null_max": float(np.max(null_f1)),
                     "null_verdicts": {k: null_verdicts.count(k) for k in (LEAK, NO_LEAK, INCONCLUSIVE)},
                     "false_positive_rate": null_verdicts.count(LEAK) / cfg.permutations})
    out["validation"]["permutation"] = perm

    reason = {LEAK: f"CI lower bound {s['ci_lo']:.3f} > chance + margin {chance + cfg.margin:.3f}",
              NO_LEAK: f"CI upper bound {s['ci_hi']:.3f} <= chance + margin {chance + cfg.margin:.3f}",
              INCONCLUSIVE: f"CI [{s['ci_lo']:.3f}, {s['ci_hi']:.3f}] straddles chance + margin "
                            f"{chance + cfg.margin:.3f}"}[v]
    if v == LEAK and cfg.permutations and perm["p_value"] > cfg.alpha:
        v, reason = INCONCLUSIVE, (f"{reason}, but the permutation test is not significant "
                                   f"(p = {perm['p_value']:.3f} > {cfg.alpha})")
    elif v == LEAK and not cfg.permutations:
        reason += " (no permutation test run)"
    elif v == NO_LEAK and cfg.permutations and perm["p_value"] <= cfg.alpha:
        v, reason = INCONCLUSIVE, (f"{reason}, but the permutation test finds a signal "
                                   f"(p = {perm['p_value']:.3f} <= {cfg.alpha}): the two models disagree")
    out["verdict"], out["reason"] = v, reason

    effect = (s["macro_f1"] - chance) / (1 - chance)
    out["prioritization"] = {"effect_size": effect,
                             "severity": severity(effect, severity_thresholds) if v == LEAK else "none"}

    if not fam_cols and single is None:
        out["attribution"] = None
        return out
    f1 = lambda t, p: f1_score(t, p, labels=classes, average="macro", zero_division=0)  # noqa: E731
    attribution = {"families": {}}
    for (fam, cols), pf in zip(fam_cols, fam_preds):
        attribution["families"][fam] = {**_score(y, pf, g, classes, cfg), "dims": int(len(cols)),
                                        "all_minus_this": paired_bootstrap_diff(
                                            y, pred, pf, g, f1, n=cfg.n_boot, seed=cfg.seed)}
    if fam_cols:
        top = max(attribution["families"], key=lambda f: attribution["families"][f]["macro_f1"])
        d = attribution["families"][top]["all_minus_this"]
        attribution["top_family"] = top
        attribution["top_family_matches_all"] = bool(d["ci_lo"] <= 0)
    if single is not None:
        d = paired_bootstrap_diff(y, pred, single_pred, g, f1, n=cfg.n_boot, seed=cfg.seed)
        attribution["single_request_size"] = {"feature": single[0], **_score(y, single_pred, g, classes, cfg),
                                              "all_minus_this": d, "matches_all": bool(d["ci_lo"] <= 0)}
    out["attribution"] = attribution
    return out
