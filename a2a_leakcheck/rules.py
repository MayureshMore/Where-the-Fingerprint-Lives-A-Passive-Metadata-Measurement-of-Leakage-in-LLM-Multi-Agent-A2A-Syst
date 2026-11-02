"""Mitigation hints and severity thresholds from a YAML rules file (default: rules.yaml)."""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_RULES = Path(__file__).with_name("rules.yaml")


def load_rules(path: Path | None = None) -> dict:
    data = yaml.safe_load(Path(path or DEFAULT_RULES).read_text()) or {}
    for i, rule in enumerate(data.get("rules", [])):
        if not {"id", "when", "hint"} <= set(rule) or not isinstance(rule["when"], dict):
            raise SystemExit(f"rule {i} in {path or DEFAULT_RULES} needs id, when (a mapping) and hint")
    return {"severity": data.get("severity", {}), "rules": data.get("rules", [])}


def facts(attribute: str, result: dict) -> dict:
    attr = result.get("attribution") or {}
    fams = attr.get("families", {})
    single = attr.get("single_request_size") or {}
    return {
        "attribute": attribute,
        "verdict": result["verdict"],
        "severity": result["prioritization"]["severity"],
        "top_family": attr.get("top_family"),
        "top_family_matches_all": attr.get("top_family_matches_all", False),
        "request_size_single_matches_all": single.get("matches_all", False),
        "family_matches_all": {f: bool(v["all_minus_this"]["ci_lo"] <= 0) for f, v in fams.items()},
        "too_few_samples": not result["validation"]["min_samples"]["ok"],
    }


def _get(f: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(f, dict) or part not in f:
            return None
        f = f[part]
    return f


def _matches(when: dict, f: dict) -> bool:
    for key, want in when.items():
        have = _get(f, key)
        if isinstance(want, list):
            if have not in want:
                return False
        elif have != want:
            return False
    return True


def hints(f: dict, rules: dict) -> list[dict]:
    return [{"id": r["id"], "hint": " ".join(str(r["hint"]).split())}
            for r in rules["rules"] if _matches(r["when"], f)]
