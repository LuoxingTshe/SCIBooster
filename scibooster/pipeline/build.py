"""Deterministic pipeline: seeds -> intent -> search -> enrichment -> screening -> snowball (screening each hop, stopping
early when a hop yields little) -> co-citation gap fill -> selection -> relations -> write out."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Callable, Literal

from ..llm.deepseek import LLM
from ..models import HopStat, Paper, Prisma, Relevance, ResearchIntent
from ..sources.openalex import OpenAlexClient
from ..sources.wos import WosClient
from ..store import CorpusStore
from ..trace import Tracer
from . import enrich, gaps, intent as intent_mod, query, relations, screen, seeds as seeds_mod, snowball

Log = Callable[[str], None]


@dataclass
class BuildParams:
    prompt: str
    seeds: list[str] = field(default_factory=list)
    years: tuple[int | None, int | None] = (None, None)
    source: Literal["wos", "openalex"] = "wos"
    n_queries: int = 3
    query_branches: list[str] = field(default_factory=list)
    wos_queries: list[str] = field(default_factory=list)  # optional fixed base queries for repeatable runs
    per_query: int = 50
    hops: int = 1
    direction: snowball.Direction = "both"
    per_node: int = 25
    frontier_size: int = 15
    prefilter_keep: int = 150
    threshold: float = 6.0
    max_papers: int = 200
    label_edges: bool = False
    label_min_score: float = 7.0
    label_max_edges: int = 150
    min_hop_yield: float = 0.1  # stop snowballing when fewer than this share of a hop's screened papers are relevant
    gap_fill: bool = True
    gap_min_count: int = 3  # a missing work must be referenced by at least this many relevant papers
    gap_max: int = 30
    exclude_retracted: bool = True


Tier = Literal["quick", "standard", "deep"]

# Presets; "standard" is the BuildParams defaults. Explicit CLI options override a preset.
TIERS: dict[str, dict] = {
    "quick": dict(n_queries=2, per_query=30, hops=0, per_node=15, frontier_size=8, prefilter_keep=60,
                  max_papers=60, gap_max=15),
    "standard": {},
    "deep": dict(n_queries=4, per_query=100, hops=3, per_node=40, frontier_size=25, prefilter_keep=300,
                 max_papers=400, gap_max=60),
}


def params_for_tier(tier: Tier, prompt: str, **overrides) -> BuildParams:
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; choose from {', '.join(TIERS)}")
    known = {f.name for f in fields(BuildParams)}
    bad = set(overrides) - known
    if bad:
        raise ValueError(f"unknown build parameter(s): {', '.join(sorted(bad))}")
    return BuildParams(prompt=prompt, **{**TIERS[tier], **{k: v for k, v in overrides.items() if v is not None}})


def build_corpus(
    params: BuildParams,
    llm: LLM,
    oa: OpenAlexClient,
    wos: WosClient | None,
    tracer: Tracer,
    out_path: Path,
    log: Log = print,
    frozen_intent: ResearchIntent | None = None,
) -> CorpusStore:
    if params.source != "wos" and (params.query_branches or params.wos_queries):
        raise ValueError("query_branches and wos_queries require source=wos")
    # Validate before any external calls, including seed resolution or intent parsing.
    query.build_wos_branch_queries(params.query_branches, params.years)
    pool = CorpusStore()
    meta = pool.corpus.meta
    meta.prompt, meta.seeds = params.prompt, list(params.seeds)
    meta.params = {k: v for k, v in asdict(params).items() if k not in ("prompt", "seeds")}
    meta.usage = tracer.usage

    # 1. Seeds (resolved first so intent parsing can use their abstracts)
    seed_papers: list[Paper] = []
    if params.seeds:
        log(f"Resolving {len(params.seeds)} seed papers…")
        seed_papers, missing = seeds_mod.resolve_seeds(params.seeds, oa, wos)
        for m in missing:
            log(f"[yellow]  ⚠ could not resolve seed: {m}[/]")
        for s in seed_papers:
            s.relevance = Relevance(score=10, reason="seed")
            pool.add(s)
            log(f"  ✓ {s.id}  {s.title[:80]} ({s.year})")

    # 2. Intent
    if frozen_intent is not None:
        # Reproducibility runs reuse a recorded intent so prefilter and screening see the same concepts.
        log("Using frozen research intent (no LLM call)…")
        intent = frozen_intent.model_copy(deep=True)
        if params.years and any(params.years):
            intent.year_range = params.years
    else:
        log("Parsing research intent (DeepSeek)…")
        intent = intent_mod.parse_intent(params.prompt, llm, seed_papers, params.years)
    meta.intent = intent
    log(f"  topic: {intent.topic}")
    log(f"  concepts: {', '.join(intent.core_concepts)}")

    # 3. Search
    if params.source == "wos":
        if wos is None:
            raise RuntimeError("source=wos needs a WOS_API_KEY")
        queries = ([query.ensure_year_clause(q, intent.year_range) for q in params.wos_queries]
                   if params.wos_queries else query.build_wos_queries(intent, llm, params.n_queries))
        queries.extend(query.build_wos_branch_queries(params.query_branches, params.years))
        queries = list(dict.fromkeys(queries))
        log(f"Running {len(queries)} WoS queries…")
        executed, hits, warns = query.run_wos_queries(queries, wos, llm, params.per_query, tracer)
        for w in warns:
            log(f"[yellow]  ⚠ {w}[/]")
        log(f"  WoS hits: {len(hits)}; enriching via OpenAlex (abstracts / references)…")
        hits = enrich.enrich_wos_hits(hits, oa)
    else:
        queries = query.build_openalex_queries(intent)
        log(f"Running {len(queries)} OpenAlex queries…")
        executed, hits, warns = query.run_openalex_queries(queries, oa, intent, params.per_query)
        for w in warns:
            log(f"[yellow]  ⚠ {w}[/]")
    meta.queries = executed
    for q in executed:
        log(f"  · {q}")
    # Every hit goes through pool.add (so a hit that duplicates a seed merges its WoS fields in); only new ones get screened
    search_new: list[Paper] = []
    excluded_year: set[str] = set()
    seen_search: set[str] = set()
    search_duplicates = 0
    for h in hits:
        key = h.doi or h.id
        if key in seen_search:
            search_duplicates += 1
            continue
        seen_search.add(key)
        if pool.has(h):
            # Merge WoS identifiers/citation fields into a seed even though it is not a new candidate.
            pool.add(h)
            search_duplicates += 1
            continue
        if not _within_years(h, params.years):
            excluded_year.add(key)
            continue
        search_new.append(pool.add(h))
    log(f"  {len(search_new)} new candidates after dedup")
    prisma = Prisma(search_duplicates=search_duplicates, excluded_out_of_year=len(excluded_year))
    meta.prisma = prisma

    # 4. Screen search hits
    to_screen = screen.prefilter(search_new, intent, params.prefilter_keep)
    log(f"LLM screening of {len(to_screen)} search hits…")
    _apply(pool, screen.llm_screen(to_screen, intent, llm, seed_papers))

    # 5. Snowball expansion, screening each hop; only relevant papers move on to the next frontier.
    #    Stop early when a hop's yield of relevant papers drops below min_hop_yield (saturation).
    frontier = seed_papers + _top_relevant(search_new, params.threshold, params.frontier_size)
    for hop in range(1, params.hops + 1):
        if not frontier:
            prisma.stop_reason = f"hop {hop}: empty frontier"
            break
        log(f"Snowball hop {hop}: expanding {params.direction} from {len(frontier)} papers…")
        cands = snowball.expand(pool, oa, frontier, hop, params.per_node, params.direction, tracer)
        out_of_year = [p for p in cands if not _within_years(p, params.years)]
        for p in out_of_year:
            pool.remove(p.id)
        prisma.excluded_out_of_year += len({p.doi or p.id for p in out_of_year})
        cands = [p for p in cands if _within_years(p, params.years)]
        to_screen = screen.prefilter(cands, intent, params.prefilter_keep)
        log(f"  {len(cands)} new candidates, BM25 prefilter -> {len(to_screen)}, LLM screening…")
        _apply(pool, screen.llm_screen(to_screen, intent, llm, seed_papers))
        relevant = [p for p in cands if p.relevance and p.relevance.score >= params.threshold]
        prisma.hops.append(HopStat(hop=hop, candidates=len(cands), screened=len(to_screen), relevant=len(relevant)))
        hop_yield = len(relevant) / len(to_screen) if to_screen else 0.0
        log(f"  hop {hop} yield: {len(relevant)}/{len(to_screen)} relevant ({hop_yield:.0%})")
        if not cands:
            prisma.stop_reason = f"hop {hop}: no new candidates"
            break
        if hop < params.hops and hop_yield < params.min_hop_yield:
            prisma.stop_reason = f"hop {hop}: yield {hop_yield:.0%} < {params.min_hop_yield:.0%}"
            log(f"[yellow]  saturation: stopping after hop {hop} ({prisma.stop_reason})[/]")
            break
        frontier = _top_relevant(cands, params.threshold, params.frontier_size)

    # 6. Co-citation gap fill: works cited by many relevant papers that snowballing never reached
    if params.gap_fill:
        relevant_pool = [p for p in pool.papers if p.is_seed or (p.relevance and p.relevance.score >= params.threshold)]
        missing = gaps.top_missing_refs(relevant_pool, pool, params.gap_min_count, params.gap_max)
        if missing:
            log(f"Gap fill: {len(missing)} works cited by >= {params.gap_min_count} relevant papers are missing "
                f"(top: {missing[0][0]} x{missing[0][1]}); fetching and screening…")
            fetched = [p for p in oa.by_ids([rid for rid, _ in missing], origin="cocited", hop=1) if not pool.has(p)]
            out_of_year = [p for p in fetched if not _within_years(p, params.years)]
            prisma.excluded_out_of_year += len({p.doi or p.id for p in out_of_year})
            fetched = [p for p in fetched if _within_years(p, params.years)]
            fetched = [pool.add(p) for p in fetched]
            _apply(pool, screen.llm_screen(fetched, intent, llm, seed_papers))
            n_rel = sum(1 for p in fetched if p.relevance and p.relevance.score >= params.threshold)
            log(f"  {n_rel}/{len(fetched)} gap-fill papers are relevant")

    # 7. Selection
    for sp in seed_papers:
        if sp.retracted:
            log(f"[yellow]  ⚠ seed {sp.id} is marked retracted in OpenAlex[/]")
    eligible = [
        p for p in pool.papers
        if not p.is_seed and p.relevance and p.relevance.score >= params.threshold
        and not (params.exclude_retracted and p.retracted)
    ]
    ranked = sorted(eligible, key=lambda p: (-p.relevance.score, -(p.cited_by_count or p.wos_times_cited or 0)))
    keep = {p.id for p in pool.papers if p.is_seed} | {p.id for p in ranked[: max(0, params.max_papers - len(seed_papers))]}
    _fill_prisma(prisma, pool, keep, params)
    log(f"Selection: {len(pool)} candidates -> {len(keep)} papers (threshold {params.threshold})")
    pool.retain(keep)

    # 8. Relations
    edges = relations.build_edges(pool)
    pool.set_edges(edges)
    log(f"Citation edges: {len(edges)}")
    if params.label_edges and edges:
        log("LLM labeling semantic dependency relations…")
        n = relations.label_edges(
            edges, pool, llm, intent.language, params.label_min_score, params.label_max_edges
        )
        log(f"  labeled {n} edges")

    pool.save(out_path)
    return pool


def _fill_prisma(prisma: Prisma, pool: CorpusStore, keep: set[str], params: BuildParams) -> None:
    """Derive the flow counts from final pool state, so they always add up."""
    prisma.identified = dict(Counter(p.origin for p in pool.papers))
    for p in pool.papers:
        if p.is_seed:
            continue
        if p.relevance is None:
            prisma.not_screened += 1
            continue
        prisma.screened += 1
        if p.relevance.score < params.threshold:
            prisma.excluded_low_relevance += 1
        elif params.exclude_retracted and p.retracted:
            prisma.excluded_retracted += 1
        elif p.id not in keep:
            prisma.excluded_over_cap += 1
    prisma.included = len(keep)


def _apply(pool: CorpusStore, scores: dict[str, Relevance]) -> None:
    for pid, rel in scores.items():
        if (p := pool.get(pid)) is not None and not p.is_seed:
            p.relevance = rel


def _within_years(paper: Paper, years: tuple[int | None, int | None]) -> bool:
    """Keep records with unknown year; reject only known publication years outside explicit bounds."""
    if paper.year is None:
        return True
    start, end = years
    return not ((start is not None and paper.year < start) or (end is not None and paper.year > end))


def _top_relevant(papers: list[Paper], threshold: float, n: int) -> list[Paper]:
    good = [p for p in papers if p.relevance and p.relevance.score >= threshold and not p.id.startswith("WOS:")]
    good.sort(key=lambda p: (-p.relevance.score, -(p.cited_by_count or 0)))
    return good[:n]
