"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _is_nonfinite(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and not math.isfinite(float(val))


def _check_ratchet(spec: dict, base_spec: dict) -> list[str]:
    problems: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return problems
    base_metrics = {m["id"]: m for m in base_spec.get("metrics") or []}
    pr_metrics = {m["id"]: m for m in spec.get("metrics") or []}
    for mid, bm in base_metrics.items():
        if mid not in pr_metrics:
            problems.append(f"ratchet: metric {mid} removed")
            continue
        pm = pr_metrics[mid]
        if bm.get("blocking") and not pm.get("blocking"):
            problems.append(f"ratchet: metric {mid} became non-blocking")
        bth, pth = bm.get("threshold") or {}, pm.get("threshold") or {}
        if "max" in bth and ("max" not in pth or pth["max"] > bth["max"]):
            problems.append(f"ratchet: metric {mid} max loosened ({pth.get('max')} > {bth['max']})")
        if "max_increase" in bth and ("max_increase" not in pth or pth["max_increase"] > bth["max_increase"]):
            problems.append(f"ratchet: metric {mid} max_increase loosened")
        if "min" in bth and ("min" not in pth or pth["min"] < bth["min"]):
            problems.append(f"ratchet: metric {mid} min loosened ({pth.get('min')} < {bth['min']})")
        if bth.get("no_significant_drop") and not pth.get("no_significant_drop"):
            problems.append(f"ratchet: metric {mid} dropped no_significant_drop")

    base_slices = {(s["name"], s["metric"]): s for s in base_spec.get("slices") or []}
    pr_slices = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for key, bs in base_slices.items():
        sname, smid = key
        if key not in pr_slices:
            problems.append(f"ratchet: slice {sname}/{smid} removed")
            continue
        ps = pr_slices[key]
        if bs.get("blocking") and not ps.get("blocking"):
            problems.append(f"ratchet: slice {sname}/{smid} became non-blocking")
        if "min" in bs and ("min" not in ps or ps["min"] < bs["min"]):
            problems.append(f"ratchet: slice {sname}/{smid} min loosened ({ps.get('min')} < {bs['min']})")
        if "max" in bs and ("max" not in ps or ps["max"] > bs["max"]):
            problems.append(f"ratchet: slice {sname}/{smid} max loosened")
        if bs.get("no_significant_drop") and not ps.get("no_significant_drop"):
            problems.append(f"ratchet: slice {sname}/{smid} dropped no_significant_drop")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    pr_metrics = pr.get("metrics") or {}
    base_metrics = base.get("metrics") or {}
    for mid, val in pr_metrics.items():
        if _is_nonfinite(val):
            problems.append(f"metric {mid} is non-finite ({val})")
    for m in spec.get("metrics") or []:
        mid = m["id"]
        if mid in base_metrics and base_metrics[mid] is not None and pr_metrics.get(mid) is None:
            problems.append(f"metric {mid} is missing/None in PR")

    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures non-empty ({len(pr['evaluator_failures'])})")

    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    pr_man = pr.get("manifest") or {}
    expected_len = int(pr_man.get("items") or 0) * len(pr_man.get("seeds") or [])
    if len(pr_rows) != expected_len:
        problems.append(
            f"row count {len(pr_rows)} != manifest {pr_man.get('items')}x{len(pr_man.get('seeds') or [])}"
        )

    pr_pairs_list = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    if len(set(pr_pairs_list)) != len(pr_pairs_list):
        problems.append("duplicate (item_id, seed) rows in PR")
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(pr_pairs_list) != base_pairs:
        problems.append("PR (item_id, seed) set differs from baseline")

    graded_ids = [
        m["id"] for m in spec.get("metrics") or []
        if m["id"] in GRADERS or any(m["id"] in r for r in base_rows)
    ]
    for mid in graded_ids:
        bad_n = sum(1 for r in pr_rows if mid not in r or r[mid] is None or _is_nonfinite(r[mid]))
        if bad_n:
            problems.append(f"metric {mid} has {bad_n} missing/None/non-finite row(s) in PR")

    base_slices = {(r.get("item_id"), r.get("seed")): sorted(r.get("slices") or []) for r in base_rows}
    for r in pr_rows:
        key = (r.get("item_id"), r.get("seed"))
        if key in base_slices and sorted(r.get("slices") or []) != base_slices[key]:
            problems.append(f"slice tags modified for {key[0]}@{key[1]}")
            break

    if base_spec is not None:
        problems.extend(_check_ratchet(spec, base_spec))
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, mid = sl["name"], sl["metric"]
        a = per_item(pr, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "min" in sl and val < sl["min"]:
            verdict = "fail"
        elif "max" in sl and val > sl["max"]:
            verdict = "fail"
        if sl.get("no_significant_drop") and val is not None:
            b = per_item(base, mid, slice_name=name)
            keys = sorted(set(a) & set(b))
            if not keys:
                verdict = "missing"
            else:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys],
                    [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(f"slice:{name}/{mid}")
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "max", "no_significant_drop") if k in sl}
        lines.append(f"  slice:{name}/{mid:<14} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
