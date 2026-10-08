"""Frozen, opt-in real API benchmark. The evaluation set is never sent to retrieval or screening."""

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

from scibooster.models import Corpus
from scibooster.pipeline.build import BuildParams, build_corpus
from scibooster.pipeline.query import build_wos_branch_queries, ensure_year_clause
from scibooster.pipeline.seeds import read_seed_file
from scibooster.store import normalize_doi

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "cases" / "classical-garden"
INPUTS = ("case.json", "core_literature.txt", "research_intent.txt", "gold.json")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_case():
    config = read_json(FIXTURE / "case.json")
    gold = read_json(FIXTURE / "gold.json")["papers"]
    seeds = read_seed_file(FIXTURE / "core_literature.txt")
    prompt = (FIXTURE / "research_intent.txt").read_text(encoding="utf-8")
    if config["schema_version"] != 1:
        raise ValueError("unsupported case schema")
    dois = [normalize_doi(g["doi"]) for g in gold]
    if len(dois) != len(set(dois)) or len(seeds) != 3:
        raise ValueError("gold DOIs must be unique and the benchmark must have three seeds")
    if set(seeds) != {g["doi"] for g in gold if g["role"] == "seed"}:
        raise ValueError("seed file and gold seed roles differ")
    kwargs = dict(config["params"])
    if set(kwargs) != {f.name for f in fields(BuildParams)} - {"prompt", "seeds"}:
        raise ValueError("BuildParams changed: explicitly version/update the frozen case instead of inheriting defaults")
    kwargs["years"] = tuple(kwargs["years"])
    params = BuildParams(prompt=prompt, seeds=seeds, **kwargs)
    if params.source != "wos" or not params.wos_queries:
        raise ValueError("this benchmark requires fixed WoS base queries")
    build_wos_branch_queries(params.query_branches, params.years)
    return config, params, gold


def expected_queries(params: BuildParams) -> list[str]:
    return list(dict.fromkeys(
        [ensure_year_clause(q, params.years) for q in params.wos_queries]
        + build_wos_branch_queries(params.query_branches, params.years)
    ))


def evaluate(corpus: Corpus, config: dict, gold: list[dict]) -> dict:
    """Count each reference once by DOI; model scores are descriptive, not independent truth."""
    start, end = config["params"]["years"]
    by_doi = {}
    for p in corpus.papers:
        for doi in {normalize_doi(v.doi) for v in [p, *p.versions] if v.doi}:
            by_doi.setdefault(doi, []).append(p)
    rows = []
    for g in gold:
        matches = by_doi.get(normalize_doi(g["doi"]), [])
        p = matches[0] if matches else None
        rows.append({**g, "hit": p is not None, "paper_id": p.id if p else None,
                     "origin": p.origin if p else None, "year": p.year if p else None,
                     "is_seed": p.is_seed if p else False,
                     "score": p.relevance.score if p and p.relevance else None,
                     "reason": p.relevance.reason if p and p.relevance else None})
    nonseeds = [r for r in rows if r["role"] != "seed"]
    independent = sum(r["hit"] and not r["is_seed"] for r in nonseeds)
    year_violations = [{"id": p.id, "year": p.year, "title": p.title} for p in corpus.papers
                       if p.year is not None and not start <= p.year <= end]
    unknown_years = [p.id for p in corpus.papers if p.year is None]
    seed_dois = {normalize_doi(g["doi"]) for g in gold if g["role"] == "seed"}
    actual_seeds = {normalize_doi(v.doi) for p in corpus.papers for v in p.versions or [p] if v.is_seed}
    errors = []
    if actual_seeds != seed_dois:
        errors.append("seed_resolution_or_seed_leakage")
    if year_violations:
        errors.append("out_of_year")
    if unknown_years:
        errors.append("unknown_year")
    if independent < config["minimum_nonseed_hits"]:
        errors.append("nonseed_recall_below_baseline")
    ids = {p.id for p in corpus.papers}
    if len(ids) != len(corpus.papers) or any(len(ps) > 1 for ps in by_doi.values()):
        errors.append("duplicate_ids_or_dois")
    if not corpus.edges or any(e.source not in ids or e.target not in ids for e in corpus.edges):
        errors.append("missing_or_invalid_edges")
    return {
        "case_id": config["case_id"], "papers": len(corpus.papers), "edges": len(corpus.edges),
        "seed_hits": sum(r["hit"] for r in rows if r["role"] == "seed"),
        "gold_hits": sum(r["hit"] for r in rows), "gold_total": len(rows),
        "nonseed_hits": independent, "nonseed_total": len(nonseeds),
        "nonseed_recall": independent / len(nonseeds) if nonseeds else None,
        "year_violations": year_violations, "unknown_years": unknown_years,
        "by_role": {role: {"hits": sum(r["hit"] for r in rows if r["role"] == role),
                           "total": sum(r["role"] == role for r in rows)}
                    for role in sorted({r["role"] for r in rows})},
        "score_histogram": dict(Counter(str(p.relevance.score) for p in corpus.papers if p.relevance and not p.is_seed)),
        "usage": corpus.meta.usage.model_dump(), "prisma": corpus.meta.prisma.model_dump() if corpus.meta.prisma else None,
        "rows": rows, "passed": not errors, "errors": errors,
    }


def write_report(out: Path, result: dict) -> None:
    write_json(out / "benchmark.json", result)
    lines = ["# 真实检索开发回归报告", "",
             f"用例：`{result['case_id']}`；检查结果：{'通过' if result['passed'] else '需关注'}。", "",
             f"语料 {result['papers']} 条，引用边 {result['edges']} 条。核对集命中 "
             f"{result['gold_hits']}/{result['gold_total']}；种子命中 {result['seed_hits']}/3；"
             f"非种子独立命中 {result['nonseed_hits']}/{result['nonseed_total']} "
             f"({result['nonseed_recall']:.1%})。",
             f"已知年份越界 {len(result['year_violations'])} 条，年份未知 {len(result['unknown_years'])} 条。", "",
             "该核对集在最初两次运行后整理，现固定用于开发回归；不是整个 PDF 包的金标准或独立盲测。"
             "未命中核对集的外部论文不等于误收。评分来自筛选模型，不等于人工精确率。", "",
             "|角色|主题|DOI|命中|年份|来源|模型分数|", "|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        lines.append(f"|{r['role']}|{r['topic']}|{r['doi']}|{'是' if r['hit'] else '否'}|"
                     f"{r['year'] or '—'}|{r['origin'] or '—'}|{r['score'] if r['score'] is not None else '—'}|")
    baseline_path = FIXTURE / "baselines.json"
    if baseline_path.exists():
        lines += ["", "## 历史比较", "", "|运行|语料|核对集|非种子|年份越界|", "|---|---|---|---|---|"]
        for b in read_json(baseline_path)["runs"]:
            lines.append(f"|{b['label']}|{b['papers']}|{b['gold_hits']}/10|{b['nonseed_hits']}/7|{b['out_of_year']}|")
        lines.append(f"|本次|{result['papers']}|{result['gold_hits']}/10|{result['nonseed_hits']}/7|{len(result['year_violations'])}|")
        lines += ["", "历史运行的 LLM 主检索式和年份过滤不同，变化不能单独归因于四个新分支。"]
    lines += ["", "检查失败项：" + (", ".join(result["errors"]) or "无"), "",
              "局限：未保存历史逐篇淘汰理由；跨 DOI 版本可能重复；高被引截断和 BM25 配额仍可能影响召回。",
              "已知年份越界剔除计数是流程记录计数，不保证跨阶段唯一，不能直接与 PRISMA identified 相加。", ""]
    (out / "benchmark.md").write_text("\n".join(lines), encoding="utf-8")


def fingerprint() -> str:
    digest = hashlib.sha256()
    paths = sorted(p for folder in ("scibooster", "renderer", "scripts")
                   for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in (".py", ".js", ".cjs"))
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_live(out: Path, config: dict, params: BuildParams, gold: list[dict], *, keep_history: bool = False, keep_cache: bool = False) -> int:
    from scibooster.config import get_settings
    from scibooster.llm.deepseek import DeepSeek
    from scibooster.obsidian import export_vault
    from scibooster.sources.cache import Cache
    from scibooster.sources.openalex import OpenAlexClient
    from scibooster.sources.wos import WosClient
    from scibooster.trace import Tracer

    settings = get_settings().model_copy(update={"deepseek_model": config["model"],
        "deepseek_temperature": config["temperature"], "wos_max_requests": config["wos_max_requests"]})
    if not settings.deepseek_api_key or not settings.wos_api_key:
        raise ValueError("DEEPSEEK_API_KEY and WOS_API_KEY are required")
    out.mkdir(parents=True, exist_ok=False)
    from scibooster.runtime import RetrievalRun

    with RetrievalRun(settings, out, kind="classical-garden", keep_history=keep_history, keep_cache=keep_cache) as run:
        snapshot = out / "inputs"
        snapshot.mkdir()
        for name in INPUTS:
            shutil.copyfile(FIXTURE / name, snapshot / name)
        if (FIXTURE / "baselines.json").exists():
            shutil.copyfile(FIXTURE / "baselines.json", snapshot / "baselines.json")
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
        manifest = {"case_id": config["case_id"], "started_at_utc": datetime.now(timezone.utc).isoformat(),
                    "git_commit": rev.stdout.strip() if rev.returncode == 0 else None,
                    "dirty_checkout": bool(status.stdout.strip()), "code_sha256": fingerprint(),
                    "inputs_sha256": {name: hashlib.sha256((snapshot / name).read_bytes()).hexdigest() for name in INPUTS},
                    "model": config["model"], "temperature": config["temperature"],
                    "cache_policy": "isolated per run; no previous HTTP cache reused",
                    "expected_queries": expected_queries(params), "status": "running"}
        write_json(out / "run.json", manifest)
        tracer = Tracer(out / "trace.jsonl")
        cache = run.cache(Cache(out / "http.sqlite"))
        try:
            llm, oa, wos = DeepSeek(settings, tracer), OpenAlexClient(settings, cache, tracer), WosClient(settings, cache, tracer)
            with (out / "console.log").open("w", encoding="utf-8") as log_file:
                def log(message):
                    print(message, flush=True)
                    log_file.write(message + "\n")
                    log_file.flush()
                store = build_corpus(params, llm, oa, wos, tracer, out / "corpus.json", log=log)
            export_vault(store.corpus, out / "obsidian", out / "obsidian")
            result = evaluate(store.corpus, config, gold)
            if store.corpus.meta.queries != manifest["expected_queries"]:
                result["errors"].append("executed_queries_differ_from_fixed_case")
                result["passed"] = False
            write_report(out, result)
            manifest["status"] = "passed" if result["passed"] else "regression"
            print(f"Report: {out / 'benchmark.md'}", flush=True)
            return_code = 0 if result["passed"] else 1
        except Exception as exc:
            manifest["status"], manifest["error_type"] = "failed", type(exc).__name__
            raise
        finally:
            manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            manifest["usage"] = tracer.usage.model_dump()
            write_json(out / "run.json", manifest)

        if return_code == 0:
            run.complete([out / "corpus.json"])
        return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Show fixed inputs and queries; no API calls")
    live = sub.add_parser("run", help="Call real APIs and evaluate; incurs quota/cost")
    live.add_argument("--out", type=Path, required=True, help="New output directory (existing directories are refused)")
    live.add_argument("--keep-history", action="store_true", help="Keep earlier completed results")
    live.add_argument("--keep-cache", action="store_true", help="Keep cache for repeat experiments")
    audit = sub.add_parser("evaluate", help="Evaluate an existing corpus offline")
    audit.add_argument("corpus", type=Path)
    audit.add_argument("--out", type=Path, required=True, help="New report directory")
    args = parser.parse_args()
    config, params, gold = load_case()
    if args.command == "plan":
        print(json.dumps({"case": config, "seeds": params.seeds, "queries": expected_queries(params),
                          "gold_total": len(gold), "nonseed_total": sum(g["role"] != "seed" for g in gold)},
                         ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        return run_live(args.out.resolve(), config, params, gold, keep_history=args.keep_history, keep_cache=args.keep_cache)
    corpus = Corpus.model_validate(read_json(args.corpus))
    result = evaluate(corpus, config, gold)
    args.out.mkdir(parents=True, exist_ok=False)
    write_report(args.out, result)
    print(f"Report: {args.out / 'benchmark.md'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
