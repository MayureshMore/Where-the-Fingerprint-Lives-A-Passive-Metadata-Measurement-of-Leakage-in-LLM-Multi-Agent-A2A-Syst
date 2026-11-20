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
permutation     perm_unit "group" (default): the permutation respects the prompt groups. Where
                every group has one label (a trace attribute), the groups' labels are permuted
                across the groups: every group keeps one label, and the number of groups per class
                is kept (with groups of different sizes, a class's sample count can change). Where
                labels vary inside a group (role samples: the agents of the traces that share a
                prompt), the labels are permuted within each group, so every group keeps its
                classes; exchanging whole label sequences between groups would leave role labels
                where they were, since every trace lists its agents in the same order. Permutation i is drawn from its own seed (seed, 7, i), so
                it does not depend on how many run or in which order. perm_unit "sample": the
                labels permuted over all samples from one stream (seed), as a2a-leakcheck 0.1.x
                did; kept to reproduce earlier reports. perm_max > R: if p after R permutations is
                in perm_window (default [0.02, 0.20]), permutations R..perm_max-1 are added and p
                is computed over all of them (off by default).
model           GBT as in the repository (models/gradient_boosted.py), with the leaf size lowered
                on training folds under 2 × 20 samples per class (gbt_min_leaf), where 20 per
                leaf would allow no split
prioritization  effect size = (macro-F1 − chance) / (1 − chance), the share of the way from
                chance to perfect; severity high / medium / low by the thresholds in rules.yaml
attribution     the same CV on each feature family alone (sizes, timing, counts and direction)
                and on one request-size feature alone, each paired against all features: the
                paired cluster-bootstrap CI of macro-F1(all) − macro-F1(family), over the same
                folds and resamples. A family matches all features when the CI's upper bound is
                at most match_margin (default 0.05): it is shown to be no more than that below
                all features (non-inferiority). no_detected_deficit keeps 0.1.x's weaker rule,
                the CI's lower bound at most 0 (no deficit was detected).
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
    perm_unit: str = "group"           # "group" (respects prompt groups) | "sample" (0.1.x)
    perm_max: int = 0                  # > permutations: extend a p-value inside perm_window to this many
    perm_window: tuple = (0.02, 0.20)
    match_margin: float = 0.05         # a family matches all features when all − family ≤ this (CI upper bound)
    fold_seed: int | None = None       # seed of the fold split (default: seed); for repeated splits


PERM_UNITS = ("group", "sample")
PERM_STREAM = 7                        # permutation i of a "group" test: default_rng([seed, 7, i])


def group_plan(y: np.ndarray, g: np.ndarray) -> dict:
    """How a group-level permutation moves labels: groups with one label exchange labels across
    those groups; groups whose labels vary keep them, permuted within the group."""
    order = np.argsort(g, kind="stable")
    names, starts, sizes = np.unique(g[order], return_index=True, return_counts=True)
    members = [order[a:a + n] for a, n in zip(starts, sizes)]
    const = [k for k, m in enumerate(members) if len(set(y[m].tolist())) == 1]
    vary = [k for k, m in enumerate(members) if len(set(y[m].tolist())) > 1]
    return {"members": members, "const": const, "vary": vary, "groups": int(len(members)),
            "within_groups": len(vary), "sizes": {int(n): int((sizes == n).sum()) for n in np.unique(sizes)}}


def permute_group(y: np.ndarray, plan: dict, rng: np.random.Generator) -> np.ndarray:
    yp = y.copy()
    mem, const = plan["members"], plan["const"]
    if len(const) > 1:
        labels = [y[mem[k][0]] for k in const]
        for k, i in zip(const, rng.permutation(len(const))):
            yp[mem[k]] = labels[i]
    for k in plan["vary"]:
        yp[mem[k]] = y[mem[k]][rng.permutation(len(mem[k]))]
    return yp


def permutations(y: np.ndarray, g: np.ndarray, cfg: Config, start: int, stop: int, plan: dict | None = None) -> list:
    """Permuted label vectors start..stop-1 of this attribute's test (see the module docstring)."""
    if cfg.perm_unit == "sample":
        rng = np.random.default_rng(cfg.seed)
        out = [rng.permutation(y) for _ in range(stop)]
        return out[start:]
    if cfg.perm_unit != "group":
        raise ValueError(f"unknown perm_unit {cfg.perm_unit!r} ({', '.join(PERM_UNITS)})")
    plan = plan or group_plan(y, g)
    return [permute_group(y, plan, np.random.default_rng([cfg.seed, PERM_STREAM, i])) for i in range(start, stop)]


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
    seed = cfg.seed if cfg.fold_seed is None else cfg.fold_seed
    return list(StratifiedGroupKFold(cfg.n_splits, shuffle=True, random_state=seed)
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


def matches(d: dict, margin: float) -> dict:
    """A family (or one feature) against all features, from the paired CI of all − this: matches_all
    when it is shown to be at most `margin` below (non-inferiority); no_detected_deficit when no
    deficit was detected (0.1.x's rule, which an imprecise estimate passes)."""
    return {"matches_all": bool(d["ci_hi"] <= margin), "no_detected_deficit": bool(d["ci_lo"] <= 0)}


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
    plan = group_plan(y, g) if cfg.perm_unit == "group" else None
    perms = permutations(y, g, cfg, 0, cfg.permutations, plan)
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

    perm = {"permutations": cfg.permutations, "alpha": cfg.alpha, "null_model": null_model, "unit": cfg.perm_unit}
    if plan is not None:
        perm["groups"] = {k: plan[k] for k in ("groups", "within_groups")}
    if cfg.permutations:
        observed = s["macro_f1"] if null_obs_pred is None else \
            float(f1_score(y, null_obs_pred, labels=classes, average="macro", zero_division=0))
        null_f1 = [f for f, _ in null_runs]
        null_verdicts = [nv for _, nv in null_runs]
        p_value = (1 + sum(f >= observed for f in null_f1)) / (len(null_f1) + 1)
        if cfg.perm_max > cfg.permutations and cfg.perm_window[0] <= p_value <= cfg.perm_window[1]:
            more = permutations(y, g, cfg, cfg.permutations, cfg.perm_max, plan)
            extra = _parallel([(_null_run, X, yp, g, classes, cfg, null_model) for yp in more], cfg.jobs)
            perm["p_value_first"] = p_value
            null_f1 += [f for f, _ in extra]
            null_verdicts += [nv for _, nv in extra]
            p_value = (1 + sum(f >= observed for f in null_f1)) / (len(null_f1) + 1)
        perm.update({"permutations_run": len(null_f1), "observed_macro_f1": observed, "p_value": p_value,
                     "null_mean": float(np.mean(null_f1)), "null_max": float(np.max(null_f1)),
                     "null_verdicts": {k: null_verdicts.count(k) for k in (LEAK, NO_LEAK, INCONCLUSIVE)},
                     "false_positive_rate": null_verdicts.count(LEAK) / len(null_f1)})
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
    attribution = {"match_rule": {"match_margin": cfg.match_margin,
                                  "matches_all": "upper bound of the paired 95% CI of all − this <= match_margin",
                                  "no_detected_deficit": "lower bound of that CI <= 0 (0.1.x's matches_all)"},
                   "families": {}}
    for (fam, cols), pf in zip(fam_cols, fam_preds):
        d = paired_bootstrap_diff(y, pred, pf, g, f1, n=cfg.n_boot, seed=cfg.seed)
        attribution["families"][fam] = {**_score(y, pf, g, classes, cfg), "dims": int(len(cols)), "all_minus_this": d,
                                        **matches(d, cfg.match_margin)}
    if fam_cols:
        top = max(attribution["families"], key=lambda f: attribution["families"][f]["macro_f1"])
        attribution["top_family"] = top
        attribution["top_family_matches_all"] = attribution["families"][top]["matches_all"]
        attribution["top_family_no_detected_deficit"] = attribution["families"][top]["no_detected_deficit"]
    if single is not None:
        d = paired_bootstrap_diff(y, pred, single_pred, g, f1, n=cfg.n_boot, seed=cfg.seed)
        attribution["single_request_size"] = {"feature": single[0], **_score(y, single_pred, g, classes, cfg),
                                              "all_minus_this": d, **matches(d, cfg.match_margin)}
    out["attribution"] = attribution
    return out
