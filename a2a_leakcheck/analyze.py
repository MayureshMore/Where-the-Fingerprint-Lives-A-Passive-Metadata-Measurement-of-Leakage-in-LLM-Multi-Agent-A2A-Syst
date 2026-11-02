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
                test: the same CV on R label permutations. The p-value is (1 + #null ≥ observed)
                / (R + 1); a LEAK whose p-value exceeds alpha becomes INCONCLUSIVE. Each permuted
                run also gets a verdict, and the share of them that read LEAK is the tool's
                false-positive rate on that data.
prioritization  effect size = (macro-F1 − chance) / (1 − chance), the share of the way from
                chance to perfect; severity high / medium / low by the thresholds in rules.yaml
attribution     the same CV on each feature family alone (sizes, timing, counts and direction)
                and on one request-size feature alone, each paired against all features
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.base import clone
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
    permutations: int = 19
    alpha: float = 0.05
    min_per_class: int = 20
    seed: int = 42
    model: str = "gbt"


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


def _model(name: str):
    if name == "gbt":
        return clone(GBTClassifier().pipeline)
    if name == "rf":
        return clone(RFClassifier().pipeline)
    raise ValueError(f"unknown model {name!r} (gbt or rf)")


def _splits(y, g, cfg: Config):
    return list(StratifiedGroupKFold(cfg.n_splits, shuffle=True, random_state=cfg.seed)
                .split(np.zeros(len(y)), y, g))


def _oof(X, y, splits, cfg: Config) -> np.ndarray:
    pred = np.empty(len(y), dtype=object)
    for tr, te in splits:
        pred[te] = _model(cfg.model).fit(X[tr], y[tr]).predict(X[te])
    return pred


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
    """Everything the report needs for one attribute. single = (name, one request-size column)."""
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
    pred = _oof(X, y, splits, cfg)
    s = _score(y, pred, g, classes, cfg)
    v = verdict(s["ci_lo"], s["ci_hi"], chance, cfg.margin)
    out["analysis"] = {**s, "model": cfg.model, "folds": cfg.n_splits}

    rng = np.random.default_rng(cfg.seed)
    null_f1, null_verdicts = [], []
    for _ in range(cfg.permutations):
        yp = rng.permutation(y)
        pp = _oof(X, yp, _splits(yp, g, cfg), cfg)
        sp = _score(yp, pp, g, classes, cfg)
        null_f1.append(sp["macro_f1"])
        null_verdicts.append(verdict(sp["ci_lo"], sp["ci_hi"], chance, cfg.margin))
    perm = {"permutations": cfg.permutations, "alpha": cfg.alpha}
    if cfg.permutations:
        p_value = (1 + sum(f >= s["macro_f1"] for f in null_f1)) / (cfg.permutations + 1)
        perm.update({"p_value": p_value, "null_mean": float(np.mean(null_f1)),
                     "null_max": float(np.max(null_f1)),
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
    out["verdict"], out["reason"] = v, reason

    effect = (s["macro_f1"] - chance) / (1 - chance)
    out["prioritization"] = {"effect_size": effect,
                             "severity": severity(effect, severity_thresholds) if v == LEAK else "none"}

    f1 = lambda t, p: f1_score(t, p, labels=classes, average="macro", zero_division=0)  # noqa: E731
    attribution = {"families": {}}
    for fam, cols in families.items():
        pf = _oof(X[:, cols], y, splits, cfg)
        attribution["families"][fam] = {**_score(y, pf, g, classes, cfg), "dims": int(len(cols)),
                                        "all_minus_this": paired_bootstrap_diff(
                                            y, pred, pf, g, f1, n=cfg.n_boot, seed=cfg.seed)}
    top = max(attribution["families"], key=lambda f: attribution["families"][f]["macro_f1"])
    d = attribution["families"][top]["all_minus_this"]
    attribution["top_family"] = top
    attribution["top_family_matches_all"] = bool(d["ci_lo"] <= 0)
    if single is not None:
        name, col = single
        ps = _oof(col.reshape(-1, 1), y, splits, cfg)
        d = paired_bootstrap_diff(y, pred, ps, g, f1, n=cfg.n_boot, seed=cfg.seed)
        attribution["single_request_size"] = {"feature": name, **_score(y, ps, g, classes, cfg),
                                              "all_minus_this": d, "matches_all": bool(d["ci_lo"] <= 0)}
    out["attribution"] = attribution
    return out
