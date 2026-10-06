# SCIBooster

A literature retrieval agent harness driven by DeepSeek. You describe a research need in natural language and supply a few core papers; SCIBooster searches **Web of Science Starter API**, uses **OpenAlex** (via [pyalex](https://github.com/J535D165/pyalex)) to fill in abstracts and citation relations, and builds a citation-linked corpus in JSON. Results are written as an **Obsidian vault** (a note per paper, a Bases table, a citation-network Canvas laid out like the dev renderer, Graph view colour groups, an overview with the PRISMA flow). A small bundled web renderer (citation network + BFS/DFS playback) is kept as a development tool. Corpora can be scored for recall against published surveys and exported to BibTeX / RIS / CSV.

```
natural language + seed papers
   │  DeepSeek: intent parsing (Chinese → English search terms, concept facets, synonyms, years)
   ▼
WoS advanced query (LLM-generated, auto-fixed on syntax errors) ──► WoS Starter search
   │  matched to OpenAlex by DOI (abstract, referenced_works, citation counts)
   ▼
BM25 prefilter → DeepSeek batched relevance scoring (anchored 0–10 rubric)
   ▼
snowball expansion: backward (references) / forward (citing works), screened each hop;
stops early when a hop's share of relevant papers falls below --min-hop-yield
   ▼
co-citation gap fill: works cited by ≥ N relevant papers but never reached are fetched and screened
   ▼
selection (retracted papers excluded) → citation edges (+ optional LLM semantic labels) → corpus.json
                                                         (with a PRISMA-style flow record)
   ▼
Obsidian vault: papers/*.md + 文献库.base + 引用图谱.canvas + 总览.md (+ .obsidian/graph.json colour groups)
```

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # fill in DEEPSEEK_API_KEY, WOS_API_KEY, OPENALEX_EMAIL
```

| Variable | Description |
|---|---|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | Default model `deepseek-chat` (OpenAI-compatible endpoint) |
| `WOS_API_KEY` | WoS Starter API key. Starter has no cited-reference data, so citation edges come entirely from OpenAlex |
| `WOS_MAX_REQUESTS` | Cap on WoS requests per run (the free tier has a low daily quota); cache hits don't count toward it |
| `OPENALEX_EMAIL` / `OPENALEX_API_KEY` | OpenAlex polite pool / optional API key |

All WoS / OpenAlex responses are cached in `.cache/http.sqlite`, so rerunning the same task uses no quota.

## CLI

```bash
# Debug: show only the parsed intent and generated queries
scibooster intent "图神经网络在药物发现中的应用" --years 2017-2025

# Pipeline build (seeds accept DOI / OpenAlex ID / WOS:UID / title; repeat --seed or use --seed-file)
scibooster build "图神经网络在药物发现中的应用" \
  -s 10.48550/arXiv.1704.01212 \
  -s "Analyzing Learned Molecular Representations for Property Prediction" \
  --years 2015-2025 --tier standard --label-edges

# Without a WoS key, search with OpenAlex instead
scibooster build "..." --source openalex --tier quick

# Agent mode: DeepSeek calls tools on its own (search / snowball / screen / add) to extend an existing corpus
# --max-papers is a hard cap: add_to_corpus refuses beyond it
scibooster agent "补充 2023 年后基于大模型的分子生成工作" --corpus corpora/<run>/corpus.json --max-steps 30 --max-papers 100

# (Re)write the Obsidian output for an existing corpus; build/agent do this automatically
scibooster obsidian corpora/<run>/corpus.json                       # → corpora/<run>/obsidian/ (open as a vault)
scibooster obsidian corpora/<run>/corpus.json --vault ~/Notes       # → ~/Notes/SCIBooster/<run>/

# Recall against the reference list of a published survey (OpenAlex only, no LLM); writes eval.json
scibooster eval   corpora/<run>/corpus.json --gold 10.1016/j.ddtec.2020.11.009

# Export for Zotero / EndNote / spreadsheets (corpus.bib / .ris / .csv next to the corpus)
scibooster export corpora/<run>/corpus.json --format bibtex --min-score 7

scibooster stats    corpora/<run>/corpus.json
scibooster traverse corpora/<run>/corpus.json --start W2606780347 --mode dfs --direction cited_by --depth 4
scibooster serve    corpora/<run>/corpus.json        # dev renderer, http://127.0.0.1:8765
```

`--tier quick|standard|deep` picks a preset; any explicit option overrides it:

| | queries | per query | max hops | per node | frontier | prefilter | max papers | gap fill max |
|---|---|---|---|---|---|---|---|---|
| quick | 2 | 30 | 0 | 15 | 8 | 60 | 60 | 15 |
| standard (default) | 3 | 50 | 1 | 25 | 15 | 150 | 200 | 30 |
| deep | 4 | 100 | 3 | 40 | 25 | 300 | 400 | 60 |

Other `build` options: `--direction backward|forward|both`; `--threshold` relevance threshold (default 6); `--min-hop-yield` saturation stop (default 0.1); `--gap-min-count` / `--no-gap-fill`; `--keep-retracted`.

`eval` caveat: a survey's reference list also contains background works outside your need, so absolute recall understates coverage. Use it to compare runs on the same gold set, and don't use a corpus seed as the gold survey (its references are snowballed directly; the command warns).

Each run produces `corpora/<slug>-<time>/`:
- `corpus.json`: the corpus (schema below)
- `trace.jsonl`: every LLM / WoS / OpenAlex / tool call (for auditing and reproducibility)
- `obsidian/`: the Obsidian vault output (unless `SCIB_OBSIDIAN_VAULT` points at your own vault, or `--no-obsidian`)
- `eval.json`, `corpus.bib|ris|csv`: written by `eval` / `export`

## corpus.json

```jsonc
{
  "meta": { "prompt": "...", "seeds": [...], "intent": {...}, "queries": ["TS=..."], "params": {...},
            "usage": { "deepseek_calls": 0, "deepseek_prompt_tokens": 0, "wos_requests": 0, ... }, "summary": null,
            "prisma": { "identified": {"seed": 2, "openalex_search": 57, "cocited": 13}, "search_duplicates": 3,
                        "not_screened": 0, "screened": 70, "excluded_low_relevance": 24, "excluded_retracted": 0,
                        "excluded_over_cap": 0, "included": 48,
                        "hops": [{"hop": 1, "candidates": 120, "screened": 120, "relevant": 9}],
                        "stop_reason": "hop 2: yield 4% < 10%", "agent_added": 0 } },
  "papers": [{
    "id": "W2606780347",            // OpenAlex ID; papers that can't be matched use "WOS:<uid>" (no citation edges)
    "doi": "...", "wos_uid": "WOS:...", "title": "...", "authors": [...], "year": 2017, "venue": "...",
    "abstract": "...", "keywords": [...], "cited_by_count": 0, "wos_times_cited": 0,
    "is_seed": true, "retracted": false,   // retracted = OpenAlex is_retracted
    "origin": "seed|wos_search|openalex_search|backward|forward|cocited|agent", "hop": 0,
    "relevance": { "score": 8, "reason": "...", "flag": null },   // flag "no_abstract" = scored from title only
    "referenced_works": [...],      // full OpenAlex reference list (includes papers outside the corpus)
    "external_refs_count": 12, "external_cited_by": 300
  }],
  "edges": [{
    "source": "W_citing", "target": "W_cited", "type": "cites", "provenance": "openalex",
    "relation": { "label": "extends|uses_method|uses_data|compares|critiques|background", "rationale": "..." } // --label-edges
  }],
  "stats": { "n_papers": 0, "n_edges": 0, "by_origin": {...}, "n_retracted": 0, "year_span": [2002, 2025] }
}
```

The schema is defined in `scibooster/models.py` (Pydantic), and `Corpus.model_validate` can validate it.

## Obsidian output

Obsidian's core Graph view cannot label or colour edges, so the citation network also goes into a **Canvas**, where positions, edge labels and colours are explicit. Both views use the dev renderer's conventions (same layout, same origin colours):

| File | Opens as | Contents |
|---|---|---|
| `总览.md` | note | need, intent, queries, Agent summary, PRISMA flow (mermaid), most-cited papers, embedded table |
| `文献库.base` | Bases table (Obsidian ≥ 1.9) | views: all papers, core (≥ 8), co-citation gap fill, title-only scores, retracted |
| `引用图谱.canvas` | Canvas | the renderer's fCoSE network layout (positions from citation links only; the year is in each card's label), cards coloured by origin, ★ = seed, edges citing → cited leaving from the facing side with relation labels/colours, a colour legend group |
| `<vault>/.obsidian/graph.json` | Graph view settings | colour groups by tag (retracted → seed → origin), matching the renderer's colours; arrows on for a fresh vault |
| `papers/*.md` | notes | properties (year, relevance, origin, `corpus_cites`, …), abstract, `cites` links and typed links (`extends`, `uses_method`, …); the Graph view and Backlinks pane work on these |

- Links are vault-relative paths (`[[SCIBooster/<run>/papers/…|Gilmer 2017]]`), so several runs can share one vault.
- Re-exporting (e.g. after `agent`) rewrites each note **above** the `%% scibooster:notes … %%` marker and keeps everything you wrote below it. Notes for papers that left the corpus are deleted only if you never wrote in them; files SCIBooster didn't generate are never touched. The Base and the Canvas are regenerated in full, so put manual Canvas edits in a copy.
- **Canvas layout**: `export_vault` pipes the graph to `renderer/layout.cjs`, which runs `NetworkLayout.run` from `renderer/static/network-layout.js` on the vendored Cytoscape + fCoSE bundles under Node.js (no npm, no network), with cards sized 320×150 and a fixed seed so re-exports are identical. Without Node.js it falls back to networkx's spring layout plus the same bounding-box separation (`separate_bounds`), and the CLI says so. About 0.6 s for 50 papers and 12 s for 400.
- **Graph view colours**: groups whose query starts with `tag:#scibooster/` are replaced on every export; your other settings and colour groups are kept, and an unreadable `graph.json` is left alone. Obsidian reads it when the vault opens, so reopen the vault if the colours don't show. (Approach adapted from [graphify](https://github.com/Graphify-Labs/graphify)'s Obsidian export; queries are built from the same tag strings the notes carry, avoiding its [#2204](https://github.com/Graphify-Labs/graphify/issues/2204) mismatch.) Local graph (the right sidebar) gives the renderer's neighbourhood focus.
- Set `SCIB_OBSIDIAN_VAULT` in `.env` to write every run into your own vault.

## Dev renderer (`renderer/`)

`scibooster serve` starts FastAPI + Cytoscape.js. It is kept for development (inspecting a corpus and checking traversal); day-to-day reading happens in Obsidian.

- **Citation network**: a relaxed [fCoSE](https://github.com/iVis-at-Bilkent/cytoscape.js-fcose) force-directed layout (`renderer/static/network-layout.js`); it replaced the earlier year-layered DAG / dagre / timeline layouts. Citation relationships alone determine positions; years remain in labels and filters. The proof-quality pass includes label bounds, followed by spacing that prevents bounding-box overlap. Choose three spacing levels, re-layout, fit the view, or expand the canvas. Hover/select a paper to emphasize its direct citations; click the background or “取消聚焦” to restore the overview. All citation edges remain available. Node size ∝ log(citation count), color = source, ★ = seed, edge color = semantic dependency label. Dense networks can still contain crossings; neighborhood focus makes individual relationships easier to follow.
- **Offline assets**: pinned Cytoscape/fCoSE browser distributions and their licenses are bundled in `renderer/static/vendor/`; rendering needs no CDN or npm build. Built-in CoSE is used if the fCoSE extension is unavailable.
- **BFS / DFS traversal**: double-click nodes to set start points (several allowed), and choose direction (references to trace sources / citing works to follow later work / both) and depth; the visit order plays back step by step, and DFS shows the lineage path.
- **Search info tab**: parsed intent, executed queries, usage, parameters, and the PRISMA-style screening flow. Paper details flag retracted papers and title-only scores.
- API: `GET /api/corpus`, `GET /api/traverse?start=&mode=&direction=&depth=`. The renderer makes no LLM calls.

## Code layout

```
scibooster/
  cli.py                 Typer CLI
  config.py models.py    configuration / data models (corpus.json schema)
  evaluate.py export.py  recall against survey references; BibTeX / RIS / CSV export
  obsidian.py            Obsidian vault output (notes, Base, Canvas, overview)
  store.py graph.py      corpus dedup/merge/persistence; citation graph and BFS/DFS
  llm/                   DeepSeek wrapper (JSON output, tool calling, retries, token accounting) + prompts
  sources/               WoS Starter client, OpenAlex (pyalex) wrapper, sqlite cache
  pipeline/              intent / seeds / query / enrich / screen / snowball / gaps / relations / build
  agent/                 tool definitions + tool-calling loop
renderer/                dev renderer: FastAPI backend (corpus + traversal API), static frontend
  layout.cjs             headless entry to NetworkLayout (Node CLI), used by the Obsidian Canvas export
  static/network-layout.js  fCoSE layout + label-aware overlap removal (shared with the Node tests)
  static/vendor/         pinned Cytoscape / layout-base / cose-base / fCoSE builds + licenses
tests/                   pytest (fake LLM + in-memory citation universe + respx-mocked WoS)
  test_network_layout.cjs  node:test layout regression suite
```

## Tests

```bash
.venv/bin/python -m pytest -q
node --test tests/test_network_layout.cjs  # offline layout regression tests; Node.js 22+
# test_obsidian.py also runs the Canvas layout through Node when it is installed, and always tests the fallback
```

CI (`.github/workflows/ci.yml`, `ubuntu-26.04`, actions v7 on the Node 24 runtime) runs the Python suite on Python 3.11 and 3.14, plus the layout tests on Node.js 22. Layout tests execute the bundled browser scripts and cover overlap, year independence, filtering, empty/disconnected graphs, spacing, the fallback layout and the headless `layout.cjs` entry point (Canvas-sized cards, reproducibility, CLI).
