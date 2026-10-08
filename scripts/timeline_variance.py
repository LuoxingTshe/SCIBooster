"""Quantify LLM-induced variance in the timeline-study retrieval.

Each replicate reruns both branches with (1) the baseline's recorded research intent frozen and (2) a copy of an
earlier run's HTTP cache, so WoS/OpenAlex answers are fixed and only DeepSeek screening varies. Stage inputs and
outputs (prefilter, screening scores, frontier, snowball candidates, gap fill) are recorded per replicate.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import itertools
import json
import shutil
import statistics
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scripts.timeline_retrieval import BRANCHES, ROOT, compare, load_baseline, load_case, paper_key, read_json, write_json
from scibooster.models import Corpus
from scibooster.pipeline import build, gaps, screen, snowball

STAGES = ("search", "hop1", "gap")


@contextlib.contextmanager
def record_stages(events: list[dict]):
    """Wrap pipeline stage functions; build_corpus looks them up on their modules at call time."""
    originals = {(screen, "prefilter"): screen.prefilter, (screen, "llm_screen"): screen.llm_screen,
                 (build, "_top_relevant"): build._top_relevant, (snowball, "expand"): snowball.expand,
                 (gaps, "top_missing_refs"): gaps.top_missing_refs}

    def prefilter(papers, intent, keep):
        kept = originals[(screen, "prefilter")](papers, intent, keep)
        events.append({"fn": "prefilter", "input": [p.id for p in papers], "kept": [p.id for p in kept]})
        return kept

    def llm_screen(papers, *args, **kwargs):
        out = originals[(screen, "llm_screen")](papers, *args, **kwargs)
        events.append({"fn": "llm_screen", "papers": {p.id: {"key": paper_key(p.doi, p.id, p.title), "title": p.title}
                                                    for p in papers},
                       "scores": {pid: r.score for pid, r in out.items()}})
        return out

    def top_relevant(papers, threshold, n):
        out = originals[(build, "_top_relevant")](papers, threshold, n)
        events.append({"fn": "top_relevant", "ids": [p.id for p in out]})
        return out

    def expand(*args, **kwargs):
        out = originals[(snowball, "expand")](*args, **kwargs)
        events.append({"fn": "expand", "ids": [p.id for p in out]})
        return out

    def top_missing_refs(*args, **kwargs):
        out = originals[(gaps, "top_missing_refs")](*args, **kwargs)
        events.append({"fn": "top_missing_refs", "ids": [rid for rid, _ in out]})
        return out

    patched = {(screen, "prefilter"): prefilter, (screen, "llm_screen"): llm_screen,
               (build, "_top_relevant"): top_relevant, (snowball, "expand"): expand,
               (gaps, "top_missing_refs"): top_missing_refs}
    for (mod, name), fn in patched.items():
        setattr(mod, name, fn)
    try:
        yield
    finally:
        for (mod, name), fn in originals.items():
            setattr(mod, name, fn)


def stage_view(events: list[dict]) -> dict:
    """Map the ordered event log onto named stages (search screening, hop 1, gap fill)."""
    by_fn: dict[str, list[dict]] = {}
    for e in events:
        by_fn.setdefault(e["fn"], []).append(e)
    # "screen_papers" events come from the rolled-back multi-vote experiment (corpora/timeline-variance-votes3*)
    pre, scr = by_fn.get("prefilter", []), by_fn.get("llm_screen") or by_fn.get("screen_papers", [])
    view = {"prefilter": {}, "scores": {}, "titles": {}}
    for name, e in zip(("search", "hop1"), pre):
        view["prefilter"][name] = {"input": len(e["input"]), "kept": sorted(e["kept"])}
    for name, e in zip(STAGES, scr):
        view["scores"][name] = e["scores"]
        view["titles"].update({pid: v["title"] for pid, v in e["papers"].items()})
    view["frontier"] = sorted(by_fn["top_relevant"][0]["ids"]) if by_fn.get("top_relevant") else []
    view["snowball"] = sorted(by_fn["expand"][0]["ids"]) if by_fn.get("expand") else []
    view["gap"] = sorted(by_fn["top_missing_refs"][0]["ids"]) if by_fn.get("top_missing_refs") else []
    return view


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def mean_pairwise(sets: list[set]) -> float:
    pairs = list(itertools.combinations(sets, 2))
    return sum(jaccard(a, b) for a, b in pairs) / len(pairs) if pairs else 1.0


def analyze(out: Path, threshold: float = 6.0) -> dict:
    meta = read_json(out / "variance-run.json")
    reps = meta["replicates"]
    _, params = load_case()
    base = load_baseline()
    source = out / "inputs" if (out / "inputs").is_dir() else Path(meta["cache_from"])
    repro1 = {b: Corpus.model_validate(read_json(source / b / "corpus.json")) for b in BRANCHES}
    result = {"replicates": reps, "overrides": meta.get("overrides", {}), "branches": {}, "vs_baseline": [], "repro1_vs_baseline": compare(repro1, params)}
    corpora = []
    for r in range(1, reps + 1):
        runs = {b: Corpus.model_validate(read_json(out / f"rep{r}" / b / "corpus.json")) for b in BRANCHES}
        corpora.append(runs)
        c = compare(runs, params)
        result["vs_baseline"].append({"rep": r, "union_recall": c["union"]["baseline_recall"],
                                      "union_papers": c["union"]["reproduced"],
                                      **{b: c["branches"][b]["baseline_recall"] for b in BRANCHES},
                                      "ds_hits": c["direct_support"]["harness_hits"], "errors": c["errors"]})
    for b in BRANCHES:
        views = [stage_view(read_json(out / f"rep{r}" / b / "stages.json")) for r in range(1, reps + 1)]
        finals = [{paper_key(p.doi, p.id, p.title) for p in runs[b].papers} for runs in corpora]
        titles = {paper_key(p.doi, p.id, p.title): p.title for runs in corpora for p in runs[b].papers}
        freq = Counter(k for s in finals for k in s)
        stages = {}
        for st in STAGES:
            score_sets = [v["scores"].get(st, {}) for v in views]
            common = set.intersection(*(set(s) for s in score_sets)) if all(score_sets) else set()
            per_paper = {pid: [s[pid] for s in score_sets] for pid in common}
            changed = {pid: xs for pid, xs in per_paper.items() if len(set(xs)) > 1}
            flips = {pid: xs for pid, xs in per_paper.items()
                     if len({x >= threshold for x in xs}) > 1}
            stages[st] = {
                "screened_per_rep": [len(s) for s in score_sets],
                "same_inputs": len({frozenset(s) for s in score_sets}) == 1,
                "common": len(common), "score_changed": len(changed), "threshold_flips": len(flips),
                "mean_abs_range": (statistics.mean(max(xs) - min(xs) for xs in per_paper.values())
                                   if per_paper else None),
                "relevant_per_rep": [sum(x >= threshold for x in s.values()) for s in score_sets],
                "flip_rows": [{"id": pid, "title": views[0]["titles"].get(pid, ""), "scores": xs}
                              for pid, xs in sorted(flips.items(), key=lambda kv: kv[0])],
            }
        result["branches"][b] = {
            "prefilter_search_identical": len({tuple(v["prefilter"].get("search", {}).get("kept", []))
                                               for v in views}) == 1,
            "prefilter_hop1_identical": len({tuple(v["prefilter"].get("hop1", {}).get("kept", []))
                                             for v in views}) == 1,
            "frontier_per_rep": [v["frontier"] for v in views],
            "frontier_identical": len({tuple(v["frontier"]) for v in views}) == 1,
            "snowball_jaccard": mean_pairwise([set(v["snowball"]) for v in views]),
            "gap_jaccard": mean_pairwise([set(v["gap"]) for v in views]),
            "final_sizes": [len(s) for s in finals],
            "final_mean_jaccard": mean_pairwise(finals),
            "final_core": len(set.intersection(*finals)), "final_union": len(set.union(*finals)),
            "inclusion_frequency": dict(Counter(freq.values())),
            "unstable_papers": [{"key": k, "title": titles[k], "in_reps": n}
                                for k, n in sorted(freq.items(), key=lambda kv: (kv[1], kv[0])) if n < reps],
            "stages": stages,
            "cache_misses": [read_json(out / f"rep{r}" / b / "usage.json") for r in range(1, reps + 1)],
        }
    write_json(out / "variance.json", result)
    write_report(out, result)
    return result


def _pct(x):
    return "—" if x is None else f"{x:.1%}"


def write_report(out: Path, r: dict) -> None:
    n = r["replicates"]
    rb = r["repro1_vs_baseline"]
    lines = ["# TimelineStudy 检索波动实验", "",
             f"参数覆盖：{json.dumps(r.get('overrides') or {}, ensure_ascii=False)}", "",
             f"{n} 次重复；每次冻结基线的研究意图，复用同一份 HTTP 缓存。WoS/OpenAlex 的返回因此固定，"
             "剩余差异只来自 DeepSeek 筛选打分及其向后续环节的传播。", "",
             "## 与基线的重合", "",
             "|运行|意图|合计覆盖|history|formal_methods|直接支持（管线 20 条）|",
             "|---|---|---|---|---|---|",
             f"|repro-1|重新解析|{_pct(rb['union']['baseline_recall'])}|"
             f"{_pct(rb['branches']['history']['baseline_recall'])}|"
             f"{_pct(rb['branches']['formal_methods']['baseline_recall'])}|{rb['direct_support']['harness_hits']}/20|"]
    for v in r["vs_baseline"]:
        lines.append(f"|rep{v['rep']}|冻结|{_pct(v['union_recall'])}|{_pct(v['history'])}|"
                     f"{_pct(v['formal_methods'])}|{v['ds_hits']}/20|")
    lines += ["", "## 各环节在重复之间的一致性", "",
              "|分支|搜索预筛相同|向前沿（滚雪球起点）相同|滚雪球候选 Jaccard|补缺 Jaccard|最终语料大小|最终两两 Jaccard|稳定核心/并集|",
              "|---|---|---|---|---|---|---|---|"]
    yes = lambda x: "是" if x else "否"
    for b, v in r["branches"].items():
        lines.append(f"|{b}|{yes(v['prefilter_search_identical'])}|{yes(v['frontier_identical'])}|"
                     f"{_pct(v['snowball_jaccard'])}|{_pct(v['gap_jaccard'])}|{'/'.join(map(str, v['final_sizes']))}|"
                     f"{_pct(v['final_mean_jaccard'])}|{v['final_core']}/{v['final_union']}|")
    lines += ["", "## 打分波动", "",
              "“共同”指每次都被送去打分的文献；“跨阈值”指至少一次 ≥6、至少一次 <6。", "",
              "|分支|环节|每次送筛|输入相同|共同|分数有变化|跨阈值|平均极差|每次相关数|",
              "|---|---|---|---|---|---|---|---|---|"]
    for b, v in r["branches"].items():
        for st, s in v["stages"].items():
            if not any(s["screened_per_rep"]):
                continue
            mar = "—" if s["mean_abs_range"] is None else f"{s['mean_abs_range']:.2f}"
            lines.append(f"|{b}|{st}|{'/'.join(map(str, s['screened_per_rep']))}|{yes(s['same_inputs'])}|"
                         f"{s['common']}|{s['score_changed']}|{s['threshold_flips']}|{mar}|"
                         f"{'/'.join(map(str, s['relevant_per_rep']))}|")
    for b, v in r["branches"].items():
        lines += ["", f"## {b}：跨阈值的文献", ""]
        rows = [(st, f) for st, s in v["stages"].items() for f in s["flip_rows"]]
        lines += [f"- [{st}] {f['title']}：{f['scores']}" for st, f in rows] or ["- 无"]
        lines += ["", f"## {b}：并非每次都入选的文献", ""]
        lines += [f"- {u['title']}（{u['in_reps']}/{n}）" for u in v["unstable_papers"]] or ["- 无"]
    lines += ["", "说明：缓存未命中时会实时请求 OpenAlex（滚雪球起点变化时可能发生），次数见 variance.json 的 cache_misses。"
              "分数一致只说明可复现，不说明判断正确。", ""]
    (out / "variance.md").write_text("\n".join(lines), encoding="utf-8")


def parse_overrides(items: list[str]) -> dict:
    """--set key=value pairs for BuildParams fields; values are JSON (numbers, null) or bare strings."""
    known = {f.name for f in dataclasses.fields(build.BuildParams)}
    out = {}
    for item in items:
        key, _, raw = item.partition("=")
        if key not in known:
            raise ValueError(f"unknown BuildParams field {key!r}")
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw
    return out


def run(out: Path, cache_from: Path, replicates: int, overrides: dict | None = None, *,
        keep_history: bool = False, keep_cache: bool = False) -> int:
    from scibooster.config import get_settings
    from scibooster.llm.deepseek import DeepSeek
    from scibooster.sources.cache import Cache
    from scibooster.sources.openalex import OpenAlexClient
    from scibooster.sources.wos import WosClient
    from scibooster.trace import Tracer

    config, params = load_case()
    overrides = overrides or {}
    params = {b: dataclasses.replace(p, **overrides) for b, p in params.items()}
    settings = get_settings().model_copy(update={"deepseek_model": config["model"],
        "deepseek_temperature": config["temperature"], "wos_max_requests": config["wos_max_requests"]})
    for b in BRANCHES:
        if not (cache_from / b / "http.sqlite").exists():
            raise FileNotFoundError(cache_from / b / "http.sqlite")
    base = load_baseline()
    out.mkdir(parents=True, exist_ok=False)
    from scibooster.runtime import RetrievalRun

    with RetrievalRun(settings, out, kind="timeline-variance", keep_history=keep_history, keep_cache=keep_cache) as run:
        for b in BRANCHES:
            target = out / "inputs" / b
            target.mkdir(parents=True)
            shutil.copyfile(cache_from / b / "corpus.json", target / "corpus.json")
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        write_json(out / "variance-run.json", {
            "started_at_utc": datetime.now(timezone.utc).isoformat(), "git_commit": rev.stdout.strip(),
            "replicates": replicates, "cache_from": str(cache_from), "intent_source": "baseline corpus meta.intent",
            "overrides": overrides,
            "model": config["model"], "temperature": config["temperature"]})
        for r in range(1, replicates + 1):
            for b in BRANCHES:
                folder = out / f"rep{r}" / b
                folder.mkdir(parents=True)
                shutil.copyfile(cache_from / b / "http.sqlite", folder / "http.sqlite")
                tracer = Tracer(folder / "trace.jsonl")
                cache = run.cache(Cache(folder / "http.sqlite"))
                llm, oa, wos = DeepSeek(settings, tracer), OpenAlexClient(settings, cache, tracer), WosClient(settings, cache, tracer)
                events: list[dict] = []
                with (folder / "console.log").open("w", encoding="utf-8") as log_file, record_stages(events):
                    def log(message):
                        print(f"[rep{r} {b}] {message}", flush=True)
                        log_file.write(message + "\n")
                    build.build_corpus(params[b], llm, oa, wos, tracer, folder / "corpus.json", log=log,
                                       frozen_intent=base[b].meta.intent)
                write_json(folder / "stages.json", events)
                write_json(folder / "usage.json", tracer.usage.model_dump())
        analyze(out)
        print(f"Report: {out / 'variance.md'}", flush=True)
        run.complete([out / f"rep{r}" / b / "corpus.json" for r in range(1, replicates + 1) for b in BRANCHES])
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("run", help="Replicate both branches with frozen intent and a copied HTTP cache (DeepSeek cost only)")
    live.add_argument("--out", type=Path, required=True)
    live.add_argument("--cache-from", type=Path, required=True, help="Earlier run dir with <branch>/http.sqlite")
    live.add_argument("--replicates", type=int, default=3)
    live.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                      help="Override a BuildParams field for this experiment, e.g. --set screen_votes=3")
    live.add_argument("--keep-history", action="store_true", help="Keep earlier completed results")
    live.add_argument("--keep-cache", action="store_true", help="Keep cache for repeat experiments")
    offline = sub.add_parser("analyze", help="Recompute the report from an existing variance directory")
    offline.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        return run(args.out.resolve(), args.cache_from.resolve(), args.replicates, parse_overrides(args.set),
                   keep_history=args.keep_history, keep_cache=args.keep_cache)
    analyze(args.out)
    print(f"Report: {args.out / 'variance.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
