"""Report (JSON, Markdown, optional HTML) and repeat mode (diff against a previous report)."""

from __future__ import annotations

import html
import json
from pathlib import Path

from a2a_leakcheck.analyze import LEAK


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


def write_markdown(report: dict, path: Path) -> None:
    c, rt, p = report["collection"], report["runtime"], report["parameters"]
    L = [f"# Leak check: {report['input']['label'] or report['input']['folder']}", "",
         f"{c['traces']} traces from {c['pcaps']} captures in `{c['folder']}` "
         f"({len(c['skipped'])} skipped, {c['stripped_copies']} analysed as stripped copies). "
         f"a2a-leakcheck {report['version']}, {report['created']}.", "",
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
            L += ["", "| Features | Dims | macro-F1 [95% CI] | All − this |", "|---|---|---|---|",
                  f"| all | {report['extraction']['role_dims'] if name == 'role' else report['extraction']['trace_dims']}"
                  f" | {_ci(r['analysis'])} | — |"]
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
        if name == "role":
            L += ["", ROLE_NOTE]
    if report.get("diff"):
        d = report["diff"]
        L += ["", "## Against the baseline", "", f"Baseline: `{d['baseline']}`.", ""]
        L += [f"- {x['attribute']}: {x['before']} → {x['after']}" for x in d["changes"]] or ["- no verdict changed"]
        if d["new_leaks"]:
            L += ["", "**New LEAK: " + ", ".join(d["new_leaks"]) + "**"]
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
        note = f"<p class='meta'>{e(ROLE_NOTE)}</p>" if r["attribute"] == "role" else ""
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
    path.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leak check: {title}</title><style>{_CSS}</style></head><body>
<h1>Leak check: {title}</h1>
<p class="meta">{c['traces']} traces from {c['pcaps']} captures · a2a-leakcheck {e(report['version'])} ·
{e(report['created'])} · {rt['total_s']:.1f} s · peak memory {rt['peak_rss_mb']:.0f} MB</p>
<div class="wrap"><table><thead><tr><th>Attribute</th><th>Verdict</th><th>Severity</th><th>macro-F1 [95% CI]</th>
<th>Chance + margin</th><th>Permutation p</th><th>False positives (permuted)</th><th>Carried by</th><th>Why, and what to do</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{vis_html}
<p class="meta">Full numbers: report.json and report.md next to this file.</p>
</body></html>
""")


def diff(new: dict, old: dict, baseline: str) -> dict:
    """Verdict changes against a previous report. A new LEAK is an attribute that is LEAK now
    and was not LEAK in the baseline (including attributes the baseline did not have)."""
    changes, new_leaks, resolved = [], [], []
    for name, r in new["attributes"].items():
        before = old.get("attributes", {}).get(name, {}).get("verdict", "absent")
        after = r["verdict"]
        if before != after:
            changes.append({"attribute": name, "before": before, "after": after})
        if after == LEAK and before != LEAK:
            new_leaks.append(name)
        if before == LEAK and after != LEAK:
            resolved.append(name)
    return {"baseline": baseline, "changes": changes, "new_leaks": new_leaks, "resolved": resolved}
