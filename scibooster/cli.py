"""SCIBooster CLI entry point."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import get_settings
from .models import Usage

app = typer.Typer(add_completion=False, help="SCIBooster: DeepSeek-driven literature retrieval agent harness (WoS Starter + OpenAlex)")
console = Console()


def _log(msg: str) -> None:
    console.print(msg)


def _parse_years(s: str | None) -> tuple[int | None, int | None]:
    if not s:
        return (None, None)
    m = re.fullmatch(r"\s*(\d{4})?\s*-\s*(\d{4})?\s*", s)
    if not m:
        if re.fullmatch(r"\d{4}", s.strip()):
            return (int(s), int(s))
        raise typer.BadParameter("year range format: 2015-2025, 2015-, -2020, or 2020")
    return (int(m.group(1)) if m.group(1) else None, int(m.group(2)) if m.group(2) else None)


def _collect_seeds(seed: list[str], seed_file: Path | None) -> list[str]:
    from .pipeline.seeds import read_seed_file

    out = list(seed or [])
    if seed_file:
        out += read_seed_file(seed_file)
    return list(dict.fromkeys(out))


def _clients(tracer, source: str):
    from .llm.deepseek import DeepSeek
    from .sources.cache import Cache
    from .sources.openalex import OpenAlexClient
    from .sources.wos import WosClient

    s = get_settings()
    cache = Cache(s.scib_cache_dir / "http.sqlite")
    try:
        llm = DeepSeek(s, tracer)
    except RuntimeError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(2)
    oa = OpenAlexClient(s, cache, tracer)
    wos = None
    if s.wos_api_key:
        wos = WosClient(s, cache, tracer)
    elif source == "wos":
        console.print("[red]WOS_API_KEY is not set. Configure .env, or use --source openalex[/]")
        raise typer.Exit(2)
    return llm, oa, wos


def _obsidian_target(corpus_path: Path, vault: Path | None = None, folder: str | None = None) -> tuple[Path, Path]:
    """(output dir, vault root). Default: <run>/obsidian as its own vault; with a vault: <vault>/SCIBooster/<run>."""
    vault = vault or get_settings().scib_obsidian_vault
    if not vault:
        out = corpus_path.parent / "obsidian"
        return out, out
    vault = vault.expanduser()
    return vault / (folder or f"SCIBooster/{corpus_path.parent.name}"), vault


def _write_obsidian(corpus, corpus_path: Path, vault: Path | None = None, folder: str | None = None) -> None:
    from .obsidian import OVERVIEW, export_vault

    out, root = _obsidian_target(corpus_path, vault, folder)
    rep = export_vault(corpus, out, root)
    kept = f" (kept your text in {rep.notes_kept_user_text})" if rep.notes_kept_user_text else ""
    console.print(f"[green]✓ Obsidian:[/] {rep.notes_written} notes{kept} → {out / OVERVIEW}")
    if rep.stale_removed:
        console.print(f"  removed {len(rep.stale_removed)} notes no longer in the corpus")
    for name in rep.stale_kept:
        console.print(f"  [yellow]kept {name}: no longer in the corpus but has your notes[/]")
    if root == out:
        console.print(f"  Open the folder [bold]{out}[/] as a vault in Obsidian (Bases need Obsidian ≥ 1.9)")


def _print_usage(u: Usage) -> None:
    console.print(
        f"[dim]Usage: DeepSeek {u.deepseek_calls} calls / {u.deepseek_prompt_tokens}+{u.deepseek_completion_tokens} tokens · "
        f"WoS {u.wos_requests} requests · OpenAlex {u.openalex_requests} requests[/]"
    )


@app.command()
def intent(
    prompt: str = typer.Argument(..., help="Natural-language research need"),
    seed: list[str] = typer.Option([], "--seed", "-s", help="Seed paper: DOI / OpenAlex ID / WOS:UID / title; repeatable"),
    years: Optional[str] = typer.Option(None, help="Year range, e.g. 2018-2025"),
    source: str = typer.Option("wos", help="wos | openalex: which query form to show"),
):
    """Parse the research intent and generate candidate queries only (no search), for debugging prompts."""
    from .pipeline import intent as intent_mod, query
    from .pipeline.seeds import resolve_seeds
    from .trace import Tracer

    tracer = Tracer()
    llm, oa, wos = _clients(tracer, "openalex")
    seeds, missing = resolve_seeds(seed, oa, wos) if seed else ([], [])
    for m in missing:
        console.print(f"[yellow]could not resolve seed: {m}[/]")
    it = intent_mod.parse_intent(prompt, llm, seeds, _parse_years(years))
    console.print_json(it.model_dump_json())
    qs = query.build_wos_queries(it, llm) if source == "wos" else query.build_openalex_queries(it)
    console.print(f"\n[bold]{source} queries:[/]")
    for q in qs:
        console.print(f"  · {q}")
    _print_usage(tracer.usage)


@app.command()
def build(
    prompt: str = typer.Argument(..., help="Natural-language research need (Chinese or English)"),
    seed: list[str] = typer.Option([], "--seed", "-s", help="Seed paper: DOI / OpenAlex ID / WOS:UID / title; repeatable"),
    seed_file: Optional[Path] = typer.Option(None, help="Seed file, one per line"),
    years: Optional[str] = typer.Option(None, help="Year range, e.g. 2018-2025"),
    source: str = typer.Option("wos", help="Primary search source: wos | openalex"),
    tier: str = typer.Option("standard", help="Preset depth: quick | standard | deep (options below override it)"),
    n_queries: Optional[int] = typer.Option(None, help="Number of WoS queries the LLM generates [tier]"),
    per_query: Optional[int] = typer.Option(None, help="Max results per query [tier]"),
    hops: Optional[int] = typer.Option(None, help="Max snowball hops; stops early on low yield [tier]"),
    direction: str = typer.Option("both", help="Snowball direction: backward | forward | both"),
    per_node: Optional[int] = typer.Option(None, help="Max references/citing works expanded per node [tier]"),
    frontier: Optional[int] = typer.Option(None, help="Max frontier nodes per hop [tier]"),
    prefilter: Optional[int] = typer.Option(None, help="Max candidates sent to LLM screening per round [tier]"),
    threshold: Optional[float] = typer.Option(None, help="Relevance threshold 0-10 [default 6]"),
    max_papers: Optional[int] = typer.Option(None, help="Max corpus size [tier]"),
    min_hop_yield: Optional[float] = typer.Option(None, help="Stop snowballing when a hop's relevant share is below this [0.1]"),
    gap_fill: bool = typer.Option(True, "--gap-fill/--no-gap-fill", help="Fetch works cited by many relevant papers but missing"),
    gap_min_count: Optional[int] = typer.Option(None, help="Gap fill: min relevant papers citing a missing work [3]"),
    keep_retracted: bool = typer.Option(False, "--keep-retracted", help="Keep papers OpenAlex marks as retracted"),
    label_edges: bool = typer.Option(False, "--label-edges", help="Have the LLM label semantic dependencies on citation edges"),
    obsidian: bool = typer.Option(True, "--obsidian/--no-obsidian", help="Also write the Obsidian vault output"),
    out: Optional[Path] = typer.Option(None, help="Output corpus.json path (default corpora/<slug>-<time>/corpus.json)"),
):
    """Run the full pipeline and build a corpus with citation relations."""
    from .pipeline.build import TIERS, build_corpus, params_for_tier
    from .store import new_run_dir
    from .trace import Tracer

    if source not in ("wos", "openalex"):
        raise typer.BadParameter("--source must be wos or openalex")
    if direction not in ("backward", "forward", "both"):
        raise typer.BadParameter("--direction must be backward / forward / both")
    if tier not in TIERS:
        raise typer.BadParameter(f"--tier must be one of {', '.join(TIERS)}")
    params = params_for_tier(
        tier, prompt, seeds=_collect_seeds(seed, seed_file), years=_parse_years(years), source=source,
        n_queries=n_queries, per_query=per_query, hops=hops, direction=direction, per_node=per_node,
        frontier_size=frontier, prefilter_keep=prefilter, threshold=threshold, max_papers=max_papers,
        min_hop_yield=min_hop_yield, gap_fill=gap_fill, gap_min_count=gap_min_count,
        exclude_retracted=not keep_retracted, label_edges=label_edges,
    )
    s = get_settings()
    run_dir = out.parent if out else new_run_dir(s.scib_corpora_dir, prompt)
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = out or run_dir / "corpus.json"
    tracer = Tracer(run_dir / "trace.jsonl")
    llm, oa, wos = _clients(tracer, source)
    store = build_corpus(params, llm, oa, wos, tracer, out_path, log=_log)
    _print_stats(store.corpus)
    _print_usage(tracer.usage)
    console.print(f"\n[green]✓ Corpus written to[/] {out_path}")
    if obsidian:
        _write_obsidian(store.corpus, out_path)


@app.command()
def agent(
    prompt: str = typer.Argument(..., help="Natural-language research need"),
    corpus: Optional[Path] = typer.Option(None, help="Continue extending an existing corpus.json"),
    seed: list[str] = typer.Option([], "--seed", "-s", help="Seed paper (when starting fresh)"),
    years: Optional[str] = typer.Option(None, help="Year range"),
    threshold: float = typer.Option(6.0, help="Relevance threshold for adding to the corpus"),
    max_papers: int = typer.Option(80, help="Hard cap on corpus size (add_to_corpus refuses beyond it)"),
    max_steps: int = typer.Option(30, help="Max agent steps"),
    max_tokens: int = typer.Option(400_000, help="DeepSeek token budget"),
    label_edges: bool = typer.Option(False, "--label-edges"),
    obsidian: bool = typer.Option(True, "--obsidian/--no-obsidian", help="Also update the Obsidian vault output"),
    out: Optional[Path] = typer.Option(None, help="Output path (default: overwrite --corpus, or a new directory)"),
):
    """DeepSeek-driven tool-calling agent that explores and extends the corpus on its own."""
    from .agent.loop import run_agent
    from .agent.tools import AgentContext
    from .models import Relevance
    from .pipeline import intent as intent_mod, relations
    from .pipeline.seeds import resolve_seeds
    from .store import CorpusStore, new_run_dir
    from .trace import Tracer

    s = get_settings()
    if corpus:
        store = CorpusStore.load(corpus)
        run_dir = corpus.parent
    else:
        store = CorpusStore()
        run_dir = new_run_dir(s.scib_corpora_dir, prompt)
    out_path = out or (corpus if corpus else run_dir / "corpus.json")
    tracer = Tracer(run_dir / "trace.jsonl", usage=store.corpus.meta.usage)
    llm, oa, wos = _clients(tracer, "openalex")

    if seed:
        found, missing = resolve_seeds(seed, oa, wos)
        for m in missing:
            console.print(f"[yellow]could not resolve seed: {m}[/]")
        for p in found:
            p.relevance = Relevance(score=10, reason="seed")
            store.add(p)
    meta = store.corpus.meta
    if meta.intent is None or not corpus:
        meta.intent = intent_mod.parse_intent(prompt, llm, [p for p in store.papers if p.is_seed], _parse_years(years))
    meta.prompt = meta.prompt or prompt
    meta.seeds = list(dict.fromkeys(meta.seeds + seed))
    meta.params.setdefault("agent_runs", []).append(
        {"prompt": prompt, "max_steps": max_steps, "threshold": threshold, "max_papers": max_papers}
    )
    console.print(f"[bold]Intent:[/] {meta.intent.topic}")

    ctx = AgentContext(corpus=store, llm=llm, oa=oa, wos=wos, intent=meta.intent, tracer=tracer, threshold=threshold,
                       max_papers=max_papers)
    if len(store) >= max_papers:
        console.print(f"[yellow]Corpus already has {len(store)} papers (cap {max_papers}); the agent can only swap papers[/]")
    try:
        run_agent(ctx, prompt, max_steps, max_tokens, log=_log)
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted; saving current corpus…[/]")
    meta.summary = ctx.summary or meta.summary
    if meta.prisma is not None:
        meta.prisma.agent_added += ctx.n_added
        meta.prisma.included = len(store)
    edges = relations.build_edges(store)
    store.set_edges(edges)
    if label_edges and edges:
        relations.label_edges(edges, store, llm, meta.intent.language)
    store.save(out_path)
    if ctx.summary:
        console.print(f"\n[bold]Agent summary:[/] {ctx.summary}")
    _print_stats(store.corpus)
    _print_usage(tracer.usage)
    console.print(f"\n[green]✓ Corpus written to[/] {out_path}")
    if obsidian:
        _write_obsidian(store.corpus, out_path)


@app.command()
def stats(corpus: Path = typer.Argument(..., exists=True)):
    """Show corpus statistics and the most-connected papers."""
    from .store import CorpusStore

    _print_stats(CorpusStore.load(corpus).finalize(), top=15)


@app.command()
def traverse(
    corpus: Path = typer.Argument(..., exists=True),
    start: list[str] = typer.Option(..., "--start", help="Start paper id; repeatable"),
    mode: str = typer.Option("bfs", help="bfs | dfs"),
    direction: str = typer.Option("both", help="refs (upstream to references) | cited_by (downstream to citing works) | both"),
    depth: int = typer.Option(3),
    limit: int = typer.Option(100),
):
    """BFS/DFS traversal over the citation graph in the terminal."""
    from .graph import build_graph, traverse as trav
    from .store import CorpusStore

    c = CorpusStore.load(corpus).finalize()
    g = build_graph(c)
    bad = [s for s in start if s not in g]
    if bad:
        console.print(f"[red]Not in corpus: {', '.join(bad)}[/]")
        raise typer.Exit(1)
    visits = trav(g, start, mode=mode, direction=direction, max_depth=depth, limit=limit)
    t = Table(title=f"{mode.upper()} · {direction} · depth≤{depth}")
    for col in ("#", "depth", "via", "id", "year", "title"):
        t.add_column(col)
    for v in visits:
        n = g.nodes[v.id]
        t.add_row(str(v.order + 1), "  " * v.depth + str(v.depth), {"refs": "↑ref", "cited_by": "↓cited"}.get(v.via, "●"),
                  v.id, str(n["year"] or ""), (n["title"] or "")[:80])
    console.print(t)


@app.command()
def serve(
    corpus: Path = typer.Argument(..., exists=True),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8765),
):
    """Dev renderer: citation DAG + BFS/DFS playback in the browser (for reading, use the Obsidian output)."""
    import uvicorn

    from renderer.server import create_app

    console.print(f"[green]Renderer running:[/] http://{host}:{port}  (Ctrl+C to quit)")
    uvicorn.run(create_app(corpus), host=host, port=port, log_level="warning")


@app.command("obsidian")
def obsidian_cmd(
    corpus: Path = typer.Argument(..., exists=True),
    vault: Optional[Path] = typer.Option(None, help="Existing vault to write into (default: SCIB_OBSIDIAN_VAULT, else <run>/obsidian)"),
    folder: Optional[str] = typer.Option(None, help="Folder inside the vault (default SCIBooster/<run>)"),
):
    """Write (or refresh) the Obsidian vault output: paper notes, a Base, a citation Canvas, an overview note."""
    from .store import CorpusStore

    if folder and not (vault or get_settings().scib_obsidian_vault):
        raise typer.BadParameter("--folder needs --vault (or SCIB_OBSIDIAN_VAULT)")
    _write_obsidian(CorpusStore.load(corpus).finalize(), corpus, vault, folder)


@app.command("eval")
def eval_cmd(
    corpus: Path = typer.Argument(..., exists=True),
    gold: list[str] = typer.Option(..., "--gold", "-g", help="Survey whose reference list is the gold set: DOI / OpenAlex ID / title; repeatable"),
    show_missed: int = typer.Option(15, help="List this many missed gold papers (most cited first)"),
    out: Optional[Path] = typer.Option(None, help="Report path (default: eval.json next to the corpus)"),
):
    """Recall of the corpus against the references of published surveys (needs OpenAlex only, no LLM)."""
    from .evaluate import recall_report
    from .pipeline.seeds import resolve_seeds
    from .sources.cache import Cache
    from .sources.openalex import OpenAlexClient
    from .store import CorpusStore
    from .trace import Tracer

    s = get_settings()
    oa = OpenAlexClient(s, Cache(s.scib_cache_dir / "http.sqlite"), Tracer())
    surveys, missing = resolve_seeds(gold, oa)
    for m in missing:
        console.print(f"[red]could not resolve gold survey: {m}[/]")
    if not surveys:
        raise typer.Exit(1)
    c = CorpusStore.load(corpus).finalize()
    rep = recall_report(c, surveys)
    for w in rep.warnings:
        console.print(f"[yellow]⚠ {w}[/]")
    for sv in surveys:
        console.print(f"Gold: {sv.id} {sv.title[:80]} ({sv.year}) · {len(sv.referenced_works)} references")
    console.print(
        f"\n[bold]Recall {rep.recall:.1%}[/] ({rep.found}/{rep.gold_size} gold papers in a corpus of {rep.corpus_size})"
        f" · gold share of corpus {rep.gold_share_of_corpus:.1%}"
    )
    if rep.recall_at:
        console.print("  " + " · ".join(f"recall@{k} {v:.1%}" for k, v in rep.recall_at.items()))
    if show_missed and rep.missed:
        missed = sorted(oa.by_ids(rep.missed), key=lambda p: -(p.cited_by_count or 0))[:show_missed]
        t = Table(title="Most-cited gold papers missing from the corpus")
        for col in ("id", "year", "cited", "title"):
            t.add_column(col)
        for p in missed:
            t.add_row(p.id, str(p.year or ""), str(p.cited_by_count or ""), p.title[:80])
        console.print(t)
    out_path = out or corpus.parent / "eval.json"
    out_path.write_text(rep.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]✓ Report written to[/] {out_path}")


@app.command("export")
def export_cmd(
    corpus: Path = typer.Argument(..., exists=True),
    fmt: str = typer.Option("bibtex", "--format", "-f", help="bibtex | ris | csv"),
    min_score: float = typer.Option(0.0, help="Only papers scoring at least this (seeds always included)"),
    out: Optional[Path] = typer.Option(None, help="Output path (default: corpus.<ext> next to the corpus)"),
):
    """Export the corpus for Zotero / EndNote (BibTeX, RIS) or spreadsheets (CSV)."""
    from .export import EXTENSIONS, export
    from .store import CorpusStore

    if fmt not in EXTENSIONS:
        raise typer.BadParameter(f"--format must be one of {', '.join(EXTENSIONS)}")
    c = CorpusStore.load(corpus).finalize()
    papers = [p for p in c.papers if p.is_seed or (p.relevance.score if p.relevance else 0) >= min_score]
    out_path = out or corpus.with_suffix(f".{EXTENSIONS[fmt]}")
    out_path.write_text(export(papers, fmt), encoding="utf-8")
    console.print(f"[green]✓ {len(papers)} papers exported to[/] {out_path}")


def _print_stats(corpus, top: int = 8) -> None:
    st = corpus.stats
    console.print(
        f"\n[bold]Corpus:[/] {st.get('n_papers')} papers ({st.get('n_seeds')} seeds) · {st.get('n_edges')} citation edges"
        f" ({st.get('n_labeled_edges')} labeled) · years {st.get('year_span')}"
    )
    console.print(f"  origins: {st.get('by_origin')}")
    if st.get("n_retracted"):
        console.print(f"  [red]{st['n_retracted']} retracted paper(s) in the corpus[/]")
    if (pr := corpus.meta.prisma) is not None:
        console.print(
            f"  flow: identified {sum(pr.identified.values())} (+{pr.search_duplicates} duplicate search hits) → "
            f"screened {pr.screened} (not screened {pr.not_screened}) → excluded low {pr.excluded_low_relevance} · "
            f"retracted {pr.excluded_retracted} · over cap {pr.excluded_over_cap} → included {pr.included}"
            + (f" · agent +{pr.agent_added}" if pr.agent_added else "")
        )
        if pr.stop_reason:
            console.print(f"  snowball stopped early: {pr.stop_reason}")
    indeg: dict[str, int] = {}
    for e in corpus.edges:
        indeg[e.target] = indeg.get(e.target, 0) + 1
    if indeg:
        by_id = {p.id: p for p in corpus.papers}
        t = Table(title="Most cited within the corpus")
        for col in ("in-corpus cites", "id", "year", "score", "title"):
            t.add_column(col)
        for pid, k in sorted(indeg.items(), key=lambda x: -x[1])[:top]:
            p = by_id[pid]
            t.add_row(str(k), pid, str(p.year or ""), str(p.relevance.score if p.relevance else ""), p.title[:70])
        console.print(t)


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main())
