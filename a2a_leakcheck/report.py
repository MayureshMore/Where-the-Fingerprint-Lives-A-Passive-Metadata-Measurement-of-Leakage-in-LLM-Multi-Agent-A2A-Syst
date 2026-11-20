"""Report (JSON, Markdown, optional HTML) and repeat mode (diff against a previous report)."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from a2a_leakcheck.analyze import LEAK, NO_LEAK


def write_json(report: dict, path: Path) -> None:
    path.write_text(json.dumps(report, indent=2, default=str))


def _ci(r: dict | None) -> str:
    if not r:
        return "—"
    return f"{r['macro_f1']:.3f} [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]"


def _rows(report: dict) -> list[dict]:
    rows = []
    for name, r in report["attributes"].items():
        attr = r.get("attribution") or {}
        perm = r["validation"].get("permutation") or {}
        top = attr.get("top_family")
        carried = "—"
        if top and r["verdict"] == LEAK:
            single = attr.get("single_request_size") or {}
            carried = (f"{single['feature']} alone" if single.get("matches_all") else
                       top.replace("_", " and ") + (" (alone matches all)" if attr["top_family_matches_all"] else ""))
        rows.append({
            "attribute": name, "verdict": r["verdict"], "severity": r["prioritization"]["severity"],
            "score": _ci(r.get("analysis")), "threshold": f"{r['threshold']:.3f}",
            "p": f"{perm['p_value']:.3f}" if "p_value" in perm else "—",
            "fpr": f"{perm['false_positive_rate']:.2f}" if "false_positive_rate" in perm else "—",
            "carried": carried, "hints": r.get("mitigations", []), "reason": r["reason"],
        })
    return rows


ROLE_NOTE = ("A role verdict holds for the topologies in the captures; a role profile need not "
             "transfer to another topology.")


def _seen_by_topology(report: dict) -> dict[str, list[str]]:
    vis = report["collection"].get("visible_agents") or {}
    return {top: sorted(r for r, n in t["roles"].items() if n) for top, t in vis.items()}


def role_notes(report: dict, name: str, r: dict) -> list[str]:
    """Notes under a role attribute: when the agents seen differ by topology, the pooled role
    score can partly reflect the topology; a role_within_<topology> score cannot."""
    notes = []
    seen = _seen_by_topology(report)
    if name == "role" and len({tuple(v) for v in seen.values()}) > 1:
        within = [k for k, x in report["attributes"].items() if x.get("within_topology")]
        best = max(seen, key=lambda t: len(seen[t]))
        notes.append("The agents seen differ by topology (" + "; ".join(
            f"{t}: {', '.join(v) or 'none'}" for t, v in seen.items()) + "): some roles occur only in some "
            "topologies, so the pooled role score can partly reflect the topology. "
            + (f"{', '.join(within)} scores role within one topology." if within else
               f"Score role within one topology with --role-within {best} (the topology in which the most "
               "agents are seen)."))
    if r.get("within_topology"):
        top = r["within_topology"]
        notes.append(f"Role scored on the {top} traces only ({r['n']} agent samples"
                     + (f"; agents seen: {', '.join(seen[top])}" if top in seen else "")
                     + "). Every sample comes from one topology, so the score cannot come from telling the "
                       "topologies apart.")
    if name == "role" or r.get("within_topology"):
        notes.append(ROLE_NOTE)
    return notes


def _vantage_md(report: dict) -> list[str]:
    v = report["input"].get("vantage")
    if not v:
        return []
    n = report["extraction"].get("empty_traces", 0)
    return [f"Vantage `{v}`: only the flows of the endpoints this observer sees (the sidecars' `vantages`). "
            f"{n} of {report['extraction']['traces']} traces show no flow there; they stay in the analysis with "
            "all-zero features, since seeing nothing is what this observer sees for them.", ""]


def _visible_md(c: dict) -> list[str]:
    """Visible agents per topology: in how many traces each listed agent carries traffic."""
    vis = c.get("visible_agents")
    if not vis:
        return []
    roles = sorted({r for t in vis.values() for r in t["roles"]})
    L = ["Visible agents per topology: traces in which each agent listed in `agent_endpoints` carries "
         "traffic. An agent never seen gives no role samples.", "",
         "| Topology | Traces | " + " | ".join(roles) + " |", "|---|---|" + "---|" * len(roles)]
    for top, t in vis.items():
        L.append(f"| {top} | {t['traces']} | " + " | ".join(
            str(t["roles"][r]) if r in t["roles"] else "—" for r in roles) + " |")
    return L + [""]


def diff_lines(d: dict) -> list[str]:
    L = ["## Against the baseline", "", f"Baseline: `{d['baseline']}`.", ""]
    if d.get("compatible") is False:
        return L + ["**Not comparable**: the verdicts were not compared because these differ (new vs baseline):", ""] + [
            f"- `{x['field']}`: {x['new']} vs {x['baseline']}" for x in d["incompatible"]]
    L += [f"- {x['attribute']}: {x['before']} → {x['after']}" for x in d["changes"]] or ["- no verdict changed"]
    if d["new_leaks"]:
        L += ["", "**New LEAK: " + ", ".join(d["new_leaks"]) + "**"]
    for x in d.get("needs_review", []):
        if isinstance(x, str):                       # reports from 0.1.x listed names only
            x = {"attribute": x, "after": "INCONCLUSIVE", "reason": "inconclusive"}
        why = ("missing from this report" if x["reason"] == "missing" else
               "INCONCLUSIVE now: the leak is not shown to be gone")
        L += ["", f"**Needs review**: {x['attribute']} (LEAK in the baseline, {why})."]
    if d.get("resolved"):
        L += ["", "Resolved (LEAK in the baseline, NO LEAK now): " + ", ".join(d["resolved"])]
    return L


def write_markdown(report: dict, path: Path) -> None:
    c, rt, p = report["collection"], report["runtime"], report["parameters"]
    L = [f"# Leak check: {report['input']['label'] or report['input']['folder']}", "",
         f"{c['traces']} traces from {c['pcaps']} captures in `{c['folder']}` "
         f"({len(c['skipped'])} skipped, {c['stripped_copies']} analysed as stripped copies). "
         f"a2a-leakcheck {report['version']}, {report['created']}.", "",
         *status_lines(report),
         *_vantage_md(report),
         f"Verdict: LEAK if the 95% CI lower bound of macro-F1 is above chance + {p['margin']}; NO LEAK "
         f"if the upper bound is at most chance + {p['margin']}; INCONCLUSIVE otherwise, or when "
         f"the minimum-sample check fails, or when a LEAK fails the label-permutation test "
         f"(p > {p['alpha']}, {p['permutations']} permutations scored with "
         f"{p.get('null_model', p['model']).upper()}). {p['folds']}-fold grouped CV, "
         f"{p['model'].upper()}, {p['n_boot']} cluster-bootstrap resamples, seed {p['seed']}.", "",
         *_visible_md(c),
         "| Attribute | Verdict | Severity | macro-F1 [95% CI] | Chance + margin | Permutation p | "
         "False positives on permuted labels | Leak carried by |", "|---|---|---|---|---|---|---|---|"]
    for r in _rows(report):
        L.append(f"| {r['attribute']} | **{r['verdict']}** | {r['severity']} | {r['score']} | {r['threshold']} | "
                 f"{r['p']} | {r['fpr']} | {r['carried']} |")
    for name, r in report["attributes"].items():
        L += ["", f"## {name}", "", f"**{r['verdict']}**: {r['reason']}.", ""]
        L.append(f"{r['n']} samples in {r['n_groups']} groups; classes "
                 + ", ".join(f"{k} {v}" for k, v in r["validation"]["min_samples"]["per_class"].items()) + ".")
        attr = r.get("attribution")
        if attr:
            ex = report["extraction"]
            dims = ex["role_dims"] if name == "role" or r.get("within_topology") else ex["trace_dims"]
            L += ["", "| Features | Dims | macro-F1 [95% CI] | All − this |", "|---|---|---|---|",
                  f"| all | {dims} | {_ci(r['analysis'])} | — |"]
            for fam, v in attr["families"].items():
                d = v["all_minus_this"]
                L.append(f"| {fam.replace('_', ' and ')} only | {v['dims']} | {_ci(v)} | {d['diff']:+.3f} "
                         f"[{d['ci_lo']:+.3f}, {d['ci_hi']:+.3f}] |")
            s = attr.get("single_request_size")
            if s:
                d = s["all_minus_this"]
                L.append(f"| {s['feature']} only | 1 | {_ci(s)} | {d['diff']:+.3f} [{d['ci_lo']:+.3f}, {d['ci_hi']:+.3f}] |")
            pr = r["prioritization"]
            L += ["", f"Effect size {pr['effect_size']:.2f} (share of the way from chance to perfect); "
                      f"severity {pr['severity']}."]
        perm = r["validation"].get("permutation") or {}
        if perm.get("permutations"):
            nv = perm["null_verdicts"]
            L += ["", f"Permutation test ({perm.get('null_model', p['model'])}: macro-F1 "
                      f"{perm.get('observed_macro_f1', r['analysis']['macro_f1']):.3f} on the real labels): "
                      f"p = {perm['p_value']:.3f}; permuted-label macro-F1 mean "
                      f"{perm['null_mean']:.3f}, max {perm['null_max']:.3f}; verdicts on permuted labels: "
                      f"{nv['LEAK']} LEAK, {nv['NO LEAK']} NO LEAK, {nv['INCONCLUSIVE']} INCONCLUSIVE."]
        for h in r.get("mitigations", []):
            L += ["", f"- **{h['id']}**: {h['hint']}"]
        for note in role_notes(report, name, r):
            L += ["", note]
    if report.get("diff"):
        L += ["", *diff_lines(report["diff"])]
    L += ["", "## Runtime", "",
          f"{rt['total_s']:.1f} s in all (" + ", ".join(f"{k} {v:.1f} s" for k, v in rt["stages_s"].items())
          + f"); peak memory {rt['peak_rss_mb']:.0f} MB in the main process, up to "
          f"{rt['peak_rss_children_mb']:.0f} MB in each of {rt.get('workers', '?')} worker processes."]
    if rt.get("peak_rss_by_stage_mb"):
        L += ["", "| Stage | Time (s) | Peak so far, main (MB) | Peak so far, one worker (MB) |", "|---|---|---|---|"]
        times = {**{k: v for k, v in rt["stages_s"].items() if k != "analysis"},
                 **{f"analysis:{k}": v for k, v in rt.get("analysis_by_attribute_s", {}).items()}}
        for k, m in rt["peak_rss_by_stage_mb"].items():
            w = m.get("worker_mb")
            L.append(f"| {k} | {times.get(k, 0):.1f} | {m['main_mb']:.0f} | {'—' if w is None else f'{w:.0f}'} |")
    path.write_text("\n".join(L) + "\n")


_CSS = """
:root { --bg:#ffffff; --fg:#1d2433; --muted:#5b6475; --line:#d9dee7; --leak:#b42318; --ok:#067647; --inc:#8a6100; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14171c; --fg:#e7eaf0; --muted:#a3abb9; --line:#2c323c; --leak:#ff8a7a; --ok:#6ce9a6; --inc:#f5c451; }
}
body { background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:0 auto; max-width:1100px; padding:24px 16px; }
h1 { font-size:22px; margin:0 0 4px; } p.meta { color:var(--muted); margin:0 0 20px; }
.wrap { overflow-x:auto; } table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th, td { border-bottom:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top; }
th { color:var(--muted); font-weight:600; font-size:13px; }
.LEAK { color:var(--leak); font-weight:700; } .NO { color:var(--ok); font-weight:700; } .INCONCLUSIVE { color:var(--inc); font-weight:700; }
ul { margin:4px 0 0; padding-left:18px; } li { margin:2px 0; }
"""


def write_html(report: dict, path: Path) -> None:
    e = html.escape
    c, rt = report["collection"], report["runtime"]
    rows = []
    for r in _rows(report):
        cls = r["verdict"].split()[0]
        hints = "".join(f"<li><b>{e(h['id'])}</b>: {e(h['hint'])}</li>" for h in r["hints"])
        note = "".join(f"<p class='meta'>{e(n)}</p>"
                       for n in role_notes(report, r["attribute"], report["attributes"][r["attribute"]]))
        rows.append(f"<tr><td>{e(r['attribute'])}</td><td class='{cls}'>{e(r['verdict'])}</td>"
                    f"<td>{e(r['severity'])}</td><td>{e(r['score'])}</td><td>{e(r['threshold'])}</td>"
                    f"<td>{e(r['p'])}</td><td>{e(r['fpr'])}</td><td>{e(r['carried'])}</td>"
                    f"<td>{e(r['reason'])}{'<ul>' + hints + '</ul>' if hints else ''}{note}</td></tr>")
    vis = c.get("visible_agents") or {}
    roles = sorted({r for t in vis.values() for r in t["roles"]})
    vis_html = "" if not vis else (
        "<h2 style='font-size:16px'>Visible agents per topology</h2><div class='wrap'><table><thead><tr><th>Topology</th>"
        "<th>Traces</th>" + "".join(f"<th>{e(r)}</th>" for r in roles) + "</tr></thead><tbody>"
        + "".join(f"<tr><td>{e(top)}</td><td>{t['traces']}</td>"
                  + "".join(f"<td>{t['roles'].get(r, '—')}</td>" for r in roles) + "</tr>"
                  for top, t in vis.items())
        + "</tbody></table></div><p class='meta'>Traces in which each listed agent carries traffic; "
          "an agent never seen gives no role samples.</p>")
    title = e(report["input"]["label"] or Path(report["input"]["folder"]).name)
    status_html = "".join("<p>" + re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e(x)) + "</p>"
                          for x in status_lines(report) if x)
    path.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leak check: {title}</title><style>{_CSS}</style></head><body>
<h1>Leak check: {title}</h1>
<p class="meta">{c['traces']} traces from {c['pcaps']} captures · a2a-leakcheck {e(report['version'])} ·
{e(report['created'])} · {rt['total_s']:.1f} s · peak memory {rt['peak_rss_mb']:.0f} MB</p>
{status_html}<div class="wrap"><table><thead><tr><th>Attribute</th><th>Verdict</th><th>Severity</th><th>macro-F1 [95% CI]</th>
<th>Chance + margin</th><th>Permutation p</th><th>False positives (permuted)</th><th>Carried by</th><th>Why, and what to do</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{vis_html}
<p class="meta">Full numbers: report.json and report.md next to this file.</p>
</body></html>
""")


ABSENT = "absent"

# Exit codes. A run that fails several checks exits with the first of PRECEDENCE that applies.
EXIT_OK, EXIT_ERROR, EXIT_LEAK, EXIT_NEW_LEAK, EXIT_INCOMPATIBLE, EXIT_POLICY = 0, 1, 2, 3, 4, 5
PRECEDENCE = (EXIT_INCOMPATIBLE, EXIT_NEW_LEAK, EXIT_LEAK, EXIT_POLICY)

# What two reports must share before their verdicts can be compared: the verdict rule, the observer
# view, the features and, per attribute present in both, its definition (class set, topology).
VERDICT_RULE = ("margin", "alpha", "permutations", "null_model", "model", "folds", "n_boot", "min_per_class")
FEATURE_FIELDS = ("schema_version", "trace_dims", "role_dims", "measurement", "retransmissions")


def feature_schema(report: dict) -> dict:
    """The feature definition a report was computed with. Reports from before the schema version was
    recorded (0.1.x) used schema 1 when their vectors have the schema-1 sizes (195 trace, 35 role)."""
    e = report.get("extraction", {})
    s = {k: e.get(k) for k in FEATURE_FIELDS}
    if s["schema_version"] is None and (s["trace_dims"], s["role_dims"]) == (195, 35):
        s["schema_version"] = 1
    s["cleartext"] = bool(report.get("parameters", {}).get("cleartext", False))
    return s


def compatibility(new: dict, old: dict) -> list[dict]:
    """Every field that differs between the two reports' verdict rule, view, features or attribute
    definitions; empty when the verdicts can be compared. The seed, the worker count and the rules
    file are not compared: they do not change what a verdict means."""
    out = []
    pn, po = new.get("parameters", {}), old.get("parameters", {})
    for k in VERDICT_RULE:
        if pn.get(k) != po.get(k):
            out.append({"field": f"parameters.{k}", "new": pn.get(k), "baseline": po.get(k)})
    vn, vo = new.get("input", {}).get("vantage"), old.get("input", {}).get("vantage")
    if vn != vo:
        out.append({"field": "input.vantage", "new": vn, "baseline": vo})
    fn, fo = feature_schema(new), feature_schema(old)
    for k in fn:
        if fn[k] != fo[k]:
            out.append({"field": f"features.{k}", "new": fn[k], "baseline": fo[k]})
    an, ao = new.get("attributes", {}), old.get("attributes", {})
    for name in [n for n in an if n in ao]:
        for k in ("classes", "within_topology"):
            x, y = an[name].get(k), ao[name].get(k)
            if k == "classes":
                x, y = sorted(x or []), sorted(y or [])
            if x != y:
                out.append({"field": f"attributes.{name}.{k}", "new": x, "baseline": y})
    return out


def diff(new: dict, old: dict, baseline: str) -> dict:
    """Verdict changes against a previous report.

    The reports must be comparable first (compatibility()); if they are not, nothing is compared and
    `compatible` is false. A new LEAK is an attribute that is LEAK now and was not LEAK in the baseline
    (including attributes the baseline did not have). A LEAK that is now INCONCLUSIVE, or that is
    missing from the new report, is listed under `needs_review` (reason inconclusive or missing), not
    as resolved: the audit no longer shows the leak but has not shown it gone. Only a LEAK that is now
    NO LEAK is listed as resolved. Every verdict change is listed under `changes`, a missing
    attribute with after = "absent"."""
    incompatible = compatibility(new, old)
    out = {"baseline": baseline, "compatible": not incompatible, "incompatible": incompatible,
           "changes": [], "new_leaks": [], "needs_review": [], "resolved": []}
    if incompatible:
        return out
    an, ao = new["attributes"], old.get("attributes", {})
    for name in list(an) + [n for n in ao if n not in an]:
        before = ao.get(name, {}).get("verdict", ABSENT)
        after = an.get(name, {}).get("verdict", ABSENT)
        if before != after:
            out["changes"].append({"attribute": name, "before": before, "after": after})
        if after == LEAK and before != LEAK:
            out["new_leaks"].append(name)
        elif before == LEAK and after == NO_LEAK:
            out["resolved"].append(name)
        elif before == LEAK and after != LEAK:
            out["needs_review"].append({"attribute": name, "before": before, "after": after,
                                        "reason": "missing" if after == ABSENT else "inconclusive"})
    return out


def release_policy(report: dict, d: dict | None = None, fail_on_leak: bool = False, strict: bool = False,
                   require: list[str] | tuple = ()) -> dict:
    """Whether the release policy the run was given is satisfied, separately from whether the audit
    completed. The default policy (no flag) checks nothing and exits 0 whatever the verdicts.

        --baseline       exit 4 if the baseline is not comparable; exit 3 on a new LEAK
        --fail-on-leak   exit 2 on any LEAK
        --strict         exit 5 on any INCONCLUSIVE
        --require A,B    exit 5 if A or B is missing or INCONCLUSIVE (it must be LEAK or NO LEAK)
    """
    attrs, s = report["attributes"], report["summary"]
    failures = []
    if d is not None:
        if not d["compatible"]:
            failures.append({"check": "baseline", "exit": EXIT_INCOMPATIBLE, "reason": "the baseline is not comparable ("
                             + ", ".join(f"{x['field']}: {x['new']} vs {x['baseline']}" for x in d["incompatible"]) + ")"})
        elif d["new_leaks"]:
            failures.append({"check": "baseline", "exit": EXIT_NEW_LEAK,
                             "reason": "new LEAK against the baseline: " + ", ".join(d["new_leaks"])})
    if fail_on_leak and s["LEAK"]:
        failures.append({"check": "fail_on_leak", "exit": EXIT_LEAK, "reason": "LEAK: " + ", ".join(s["LEAK"])})
    if strict and s["INCONCLUSIVE"]:
        failures.append({"check": "strict", "exit": EXIT_POLICY, "reason": "INCONCLUSIVE: " + ", ".join(s["INCONCLUSIVE"])})
    missing = [x for x in require if x not in attrs]
    undecided = [x for x in require if x in attrs and attrs[x]["verdict"] not in (LEAK, NO_LEAK)]
    if missing:
        failures.append({"check": "require", "exit": EXIT_POLICY, "reason": "required, missing: " + ", ".join(missing)})
    if undecided:
        failures.append({"check": "require", "exit": EXIT_POLICY,
                         "reason": "required, INCONCLUSIVE: " + ", ".join(undecided)})
    codes = {f["exit"] for f in failures}
    lost = {x["attribute"]: x for x in (d or {}).get("needs_review", [])} if d is not None and d["compatible"] else {}
    review = [{"attribute": x, "reason": "INCONCLUSIVE" + ("; LEAK in the baseline" if x in lost else "")}
              for x in s["INCONCLUSIVE"]]
    review += [{"attribute": x, "reason": "missing; LEAK in the baseline"}
               for x, v in lost.items() if v["reason"] == "missing"]
    return {
        "audit_completed": True,
        "verdicts": {v: len(s[v]) for v in (LEAK, NO_LEAK, "INCONCLUSIVE")},
        "release_policy": {
            "configured": d is not None or fail_on_leak or strict or bool(require),
            "checks": {"baseline": d["baseline"] if d is not None else None, "fail_on_leak": fail_on_leak,
                       "strict": strict, "require": list(require)},
            "satisfied": not failures, "failures": failures,
            "exit_code": next((c for c in PRECEDENCE if c in codes), EXIT_OK)},
        "for_review": review,
    }


def status_lines(report: dict) -> list[str]:
    """Header lines: whether the audit completed, and (separately) whether the release policy holds."""
    st = report.get("status")
    if not st:
        return []
    v, rp = st["verdicts"], st["release_policy"]
    L = [f"**Audit completed**: {sum(v.values())} attributes, {v['LEAK']} LEAK, {v['NO LEAK']} NO LEAK, "
         f"{v['INCONCLUSIVE']} INCONCLUSIVE."]
    if not rp["configured"]:
        L.append("**Release policy**: none configured, so the run exits 0 whatever the verdicts (gate a release "
                 "with --baseline, --fail-on-leak, --strict or --require).")
    elif rp["satisfied"]:
        on = [k for k, x in rp["checks"].items() if x]
        L.append(f"**Release policy satisfied** ({', '.join(on)}); exit 0.")
    else:
        L.append(f"**Release policy not satisfied**, exit {rp['exit_code']}: "
                 + "; ".join(f["reason"] for f in rp["failures"]) + ".")
    if st["for_review"]:
        L.append("**For review**: " + ", ".join(f"{x['attribute']} ({x['reason']})" for x in st["for_review"]) + ".")
    return [x for line in L for x in (line, "")]
