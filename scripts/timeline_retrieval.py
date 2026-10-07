"""Replay the two-branch retrieval of the timeline-study case and compare it with the 2026-10-07 baseline.

Only retrieval is reproduced (build_corpus per branch). DOI identity checks, Crossref audits and the
timeline reconstruction are out of scope. The comparison sets are read only after retrieval finishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

from scibooster.models import Corpus, Paper
from scibooster.pipeline.build import BuildParams, build_corpus
from scibooster.pipeline.query import ensure_year_clause
from scibooster.store import normalize_doi

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "tests" / "cases" / "timeline-study"
RETRIEVAL = CASE / "retrieval"
VERIFICATION = CASE / "input" / "data" / "doi-verification-2026-10-07"
BRANCHES = ("history", "formal_methods")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_case() -> tuple[dict, dict[str, BuildParams]]:
    config = read_json(RETRIEVAL / "case.json")
    if config["schema_version"] != 1:
        raise ValueError("unsupported case schema")
    known = {f.name for f in fields(BuildParams)} - {"prompt", "seeds"}
    params = {}
    for name in BRANCHES:
        b = config["branches"][name]
        kwargs = dict(b["params"])
        if set(kwargs) != known:
            raise ValueError("BuildParams changed: version the frozen case instead of inheriting defaults")
        kwargs["years"] = tuple(kwargs["years"])
        params[name] = BuildParams(prompt=b["prompt"], seeds=b["seeds"], **kwargs)
        if params[name].source != "wos" or not params[name].wos_queries:
            raise ValueError("this case requires fixed WoS base queries")
    return config, params


def expected_queries(params: BuildParams) -> list[str]:
    return list(dict.fromkeys(ensure_year_clause(q, params.years) for q in params.wos_queries))


def paper_key(doi: str | None, pid: str | None, title: str | None) -> str:
    """DOI first; records without DOI fall back to OpenAlex id, then a folded title."""
    if d := normalize_doi(doi):
        return "doi:" + d
    if pid and pid.startswith("W"):
        return "oa:" + pid
    return "title:" + " ".join((title or "").casefold().split())


def _key(p: Paper) -> str:
    return paper_key(p.doi, p.id, p.title)


def load_baseline() -> dict[str, Corpus]:
    config = read_json(RETRIEVAL / "case.json")
    return {name: Corpus.model_validate(read_json(RETRIEVAL / config["branches"][name]["baseline_corpus"]))
            for name in BRANCHES}


def harness_direct_support() -> list[dict]:
    """Direct-support records whose DOI was among the 79 harness candidates (the rest came from targeted lookups)."""
    candidates = read_json(VERIFICATION / "not_in_direct_doi.json")["screened_harness_candidates"]
    found = {normalize_doi(c["doi"]): c["branches"] for c in candidates if c.get("doi")}
    rows = []
    for r in read_json(VERIFICATION / "direct_support_doi.json")["records"]:
        d = normalize_doi(r["doi"])
        if d in found:
            seed = any(x.get("is_seed") for x in r.get("discovery", []))
            rows.append({"id": r["id"], "doi": d, "title": r["title"], "branches": found[d], "is_seed": seed})
    return rows


def compare(runs: dict[str, Corpus], params: dict[str, BuildParams]) -> dict:
    base = load_baseline()
    candidates = read_json(VERIFICATION / "not_in_direct_doi.json")["screened_harness_candidates"]
    result: dict = {"branches": {}, "errors": []}
    for name in BRANCHES:
        b, r = base[name], runs[name]
        bk = {_key(p): p for p in b.papers}
        rk = {_key(p): p for p in r.papers}
        shared = bk.keys() & rk.keys()
        seeds_expected = {normalize_doi(s) for s in params[name].seeds}
        seeds_found = {normalize_doi(p.doi) for p in r.papers if p.is_seed}
        queries_ok = r.meta.queries == expected_queries(params[name])
        if seeds_found != seeds_expected:
            result["errors"].append(f"{name}: seed_resolution")
        if not queries_ok:
            result["errors"].append(f"{name}: executed_queries_differ_from_fixed_case")
        if len(rk) != len(r.papers):
            result["errors"].append(f"{name}: duplicate_keys")
        by_origin = {}
        for origin in sorted({p.origin for p in b.papers}):
            keys = [k for k, p in bk.items() if p.origin == origin]
            by_origin[origin] = {"baseline": len(keys), "reproduced": sum(k in rk for k in keys)}
        result["branches"][name] = {
            "baseline_papers": len(b.papers), "reproduced_papers": len(r.papers),
            "shared": len(shared), "baseline_recall": len(shared) / len(bk) if bk else None,
            "jaccard": len(shared) / len(bk.keys() | rk.keys()) if bk or rk else None,
            "baseline_by_origin": by_origin,
            "reproduced_origins": dict(Counter(p.origin for p in r.papers)),
            "seeds_resolved": f"{len(seeds_found & seeds_expected)}/{len(seeds_expected)}",
            "queries_match": queries_ok,
            "baseline_edges": len(b.edges), "reproduced_edges": len(r.edges),
            "usage": r.meta.usage.model_dump(), "prisma": r.meta.prisma.model_dump() if r.meta.prisma else None,
            "missing": [{"key": k, "title": bk[k].title, "year": bk[k].year, "origin": bk[k].origin}
                        for k in sorted(bk.keys() - rk.keys())],
            "new": [{"key": k, "title": rk[k].title, "year": rk[k].year, "origin": rk[k].origin,
                     "score": rk[k].relevance.score if rk[k].relevance else None}
                    for k in sorted(rk.keys() - bk.keys())],
        }
    cand_keys = {paper_key(c.get("doi"), c.get("id"), c.get("title")) for c in candidates}
    run_keys = {_key(p) for c in runs.values() for p in c.papers}
    base_keys = {_key(p) for c in base.values() for p in c.papers}
    if cand_keys != base_keys:
        result["errors"].append("baseline_corpora_differ_from_79_candidate_list")
    ds = harness_direct_support()
    ds_rows = [{**d, "hit": "doi:" + d["doi"] in run_keys} for d in ds]
    nonseed = [d for d in ds_rows if not d["is_seed"]]
    result["union"] = {"baseline": len(cand_keys), "reproduced": len(run_keys),
                       "shared": len(cand_keys & run_keys),
                       "baseline_recall": len(cand_keys & run_keys) / len(cand_keys)}
    result["direct_support"] = {"harness_total": len(ds_rows), "harness_hits": sum(d["hit"] for d in ds_rows),
                                "nonseed_total": len(nonseed), "nonseed_hits": sum(d["hit"] for d in nonseed),
                                "rows": ds_rows}
    result["passed"] = not result["errors"]
    return result


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.1%}"


def write_report(out: Path, result: dict, label: str) -> None:
    write_json(out / "comparison.json", result)
    u, ds = result["union"], result["direct_support"]
    lines = ["# TimelineStudy 检索复现对比", "",
             f"对象：`{label}`；结构检查：{'通过' if result['passed'] else '需关注'}。", "",
             f"合并候选：基线 {u['baseline']} 条，本次 {u['reproduced']} 条，重合 {u['shared']} 条"
             f"（基线覆盖 {_pct(u['baseline_recall'])}）。",
             f"直接支持记录中由检索管线发现的 {ds['harness_total']} 条：本次命中 {ds['harness_hits']}；"
             f"其中非种子 {ds['nonseed_hits']}/{ds['nonseed_total']}。", "",
             "|分支|基线|本次|重合|基线覆盖|Jaccard|种子|检索式一致|DeepSeek 调用|WoS 请求|",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, b in result["branches"].items():
        lines.append(f"|{name}|{b['baseline_papers']}|{b['reproduced_papers']}|{b['shared']}|"
                     f"{_pct(b['baseline_recall'])}|{_pct(b['jaccard'])}|{b['seeds_resolved']}|"
                     f"{'是' if b['queries_match'] else '否'}|{b['usage']['deepseek_calls']}|{b['usage']['wos_requests']}|")
    lines += ["", "## 按基线来源统计的保留情况", "", "|分支|来源|基线|本次仍在|", "|---|---|---|---|"]
    for name, b in result["branches"].items():
        for origin, v in b["baseline_by_origin"].items():
            lines.append(f"|{name}|{origin}|{v['baseline']}|{v['reproduced']}|")
    lines += ["", "## 直接支持记录（管线发现部分）", "", "|ID|分支|种子|命中|题名|", "|---|---|---|---|---|"]
    for d in ds["rows"]:
        lines.append(f"|{d['id']}|{','.join(d['branches'])}|{'是' if d['is_seed'] else '否'}|"
                     f"{'是' if d['hit'] else '否'}|{d['title']}|")
    for name, b in result["branches"].items():
        lines += ["", f"## {name}：基线有、本次缺", ""]
        lines += [f"- {m['title']}（{m['year']}，{m['origin']}）" for m in b["missing"]] or ["- 无"]
        lines += ["", f"## {name}：本次新增", ""]
        lines += [f"- {m['title']}（{m['year']}，{m['origin']}，分数 {m['score']}）" for m in b["new"]] or ["- 无"]
    lines += ["", "检查失败项：" + (", ".join(result["errors"]) or "无"), "",
              "说明：相关度由实时模型评分，WoS/OpenAlex 索引也会变化，重合率衡量的是检索结果的复现程度，"
              "不是检索质量或事实支持。直接支持清单中另有 21 条来自定向 DOI/题名核对，不属于本复现范围。", ""]
    (out / "comparison.md").write_text("\n".join(lines), encoding="utf-8")


def run_live(out: Path, config: dict, params: dict[str, BuildParams]) -> int:
    from scibooster.config import get_settings
    from scibooster.llm.deepseek import DeepSeek
    from scibooster.sources.cache import Cache
    from scibooster.sources.openalex import OpenAlexClient
    from scibooster.sources.wos import WosClient
    from scibooster.trace import Tracer

    settings = get_settings().model_copy(update={"deepseek_model": config["model"],
        "deepseek_temperature": config["temperature"], "wos_max_requests": config["wos_max_requests"]})
    if not settings.deepseek_api_key or not settings.wos_api_key:
        raise ValueError("DEEPSEEK_API_KEY and WOS_API_KEY are required")
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(RETRIEVAL / "case.json", out / "case.json")
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    status = subprocess.run(["git", "status", "--porcelain", "scibooster"], cwd=ROOT, capture_output=True, text=True)
    manifest = {"case_id": config["case_id"], "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "git_commit": rev.stdout.strip() if rev.returncode == 0 else None,
                "dirty_scibooster": bool(status.stdout.strip()),
                "case_sha256": hashlib.sha256((RETRIEVAL / "case.json").read_bytes()).hexdigest(),
                "cache_policy": "isolated per branch; no previous HTTP cache reused", "status": "running", "usage": {}}
    write_json(out / "run.json", manifest)
    runs = {}
    try:
        for name in BRANCHES:
            folder = out / name
            folder.mkdir()
            tracer = Tracer(folder / "trace.jsonl")
            cache = Cache(folder / "http.sqlite")
            llm, oa, wos = DeepSeek(settings, tracer), OpenAlexClient(settings, cache, tracer), WosClient(settings, cache, tracer)
            with (folder / "console.log").open("w", encoding="utf-8") as log_file:
                def log(message):
                    print(f"[{name}] {message}", flush=True)
                    log_file.write(message + "\n")
                    log_file.flush()
                store = build_corpus(params[name], llm, oa, wos, tracer, folder / "corpus.json", log=log)
            manifest["usage"][name] = tracer.usage.model_dump()
            runs[name] = store.corpus
        result = compare(runs, params)
        write_report(out, result, out.name)
        manifest["status"] = "passed" if result["passed"] else "structural_errors"
        print(f"Report: {out / 'comparison.md'}", flush=True)
        return 0 if result["passed"] else 1
    except Exception as exc:
        manifest["status"], manifest["error_type"] = "failed", type(exc).__name__
        raise
    finally:
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(out / "run.json", manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Show the frozen branches and queries; no API calls")
    live = sub.add_parser("run", help="Call real DeepSeek/WoS/OpenAlex for both branches; incurs quota/cost")
    live.add_argument("--out", type=Path, required=True, help="New output directory (existing directories are refused)")
    audit = sub.add_parser("compare", help="Compare an existing run directory (<dir>/<branch>/corpus.json) offline")
    audit.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    config, params = load_case()
    if args.command == "plan":
        print(json.dumps({name: {"seeds": p.seeds, "queries": expected_queries(p)} for name, p in params.items()},
                         ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        return run_live(args.out.resolve(), config, params)
    runs = {name: Corpus.model_validate(read_json(args.run_dir / name / "corpus.json")) for name in BRANCHES}
    result = compare(runs, params)
    write_report(args.run_dir, result, args.run_dir.name)
    print(f"Report: {args.run_dir / 'comparison.md'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
