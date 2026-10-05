---
name: scibooster
description: Run, test, debug, or extend this repo's SCIBooster literature-retrieval harness (DeepSeek + WoS Starter/OpenAlex → citation-linked corpus.json → Obsidian vault output (notes, Base, Canvas) + dev DAG renderer, recall eval, BibTeX/RIS/CSV export). Use when the task is to build or expand a corpus, evaluate or export it, inspect corpus stats, start the renderer, run the test suite, or change pipeline / agent / source / renderer code in this project. Triggers on 构建语料库, 跑一遍 pipeline, 评估召回, 导出文献, 生成 Obsidian, 启动渲染器, 跑测试, scibooster build/agent/obsidian/eval/export/serve.
---

# SCIBooster (project skill)

Read `PROGRESS.md` first when resuming: it holds env status, the last live run, and open decisions.

## Invariants

- Run every command **from the project root**. `config.py` loads `.env` relative to CWD; this is a confirmed decision, do not "fix" it.
- Never print, copy, or log the value of `DEEPSEEK_API_KEY` / `WOS_API_KEY`. Check presence with `grep -c '^DEEPSEEK_API_KEY=.\+' .env`.
- `WOS_API_KEY` may be empty → use `--source openalex` for live runs. The WoS path is mock-tested only.
- Use `.venv/bin/...` binaries; no global installs.
- Live runs cost DeepSeek tokens and API quota. Debug with `intent` (≈2 calls) before `build`; HTTP responses are cached in `.cache/http.sqlite`, so re-runs are cheap.

## Commands

```bash
.venv/bin/scibooster intent "<need>" --years 2018-2025 --source openalex      # cheap: intent + queries only
.venv/bin/scibooster build  "<need>" -s <DOI|title|W-id> --source openalex --tier quick   # quick|standard|deep
.venv/bin/scibooster agent  "<extra direction>" --corpus corpora/<run>/corpus.json --max-steps 30 --max-papers 100  # hard cap
.venv/bin/scibooster eval   corpora/<run>/corpus.json --gold <survey DOI>   # recall vs survey refs; no LLM
.venv/bin/scibooster export corpora/<run>/corpus.json -f bibtex|ris|csv
.venv/bin/scibooster obsidian corpora/<run>/corpus.json [--vault PATH]   # build/agent already do this
.venv/bin/scibooster stats    corpora/<run>/corpus.json
.venv/bin/scibooster traverse corpora/<run>/corpus.json --start <W-id> --mode dfs --direction cited_by
.venv/bin/scibooster serve    corpora/<run>/corpus.json        # dev renderer only; http://127.0.0.1:8765 (CDN JS)
.venv/bin/python -m pytest -q                                   # offline: FakeLLM + in-memory citation universe + respx
```

Every run writes `trace.jsonl` next to the corpus; token usage is in `corpus.meta.usage`, the screening flow in `corpus.meta.prisma`. Use `eval` on the same gold survey to compare runs before/after a pipeline change.

## Where things live

| Change | File |
|---|---|
| Pipeline stage order / selection | `scibooster/pipeline/build.py` |
| Relevance screening (BM25 prefilter + LLM batches) | `scibooster/pipeline/screen.py` |
| Snowball (backward/forward) | `scibooster/pipeline/snowball.py` |
| Co-citation gap fill | `scibooster/pipeline/gaps.py` |
| Tier presets | `TIERS` in `scibooster/pipeline/build.py` |
| Recall eval / export | `scibooster/evaluate.py`, `scibooster/export.py` |
| All LLM prompts | `scibooster/llm/prompts.py` |
| Agent tools / loop | `scibooster/agent/tools.py`, `agent/loop.py` |
| Dedup / merge rules | `scibooster/store.py` (`_ORIGIN_RANK`, `_merge_into`) |
| corpus.json schema | `scibooster/models.py` |
| Obsidian output (user-facing; see json-canvas / obsidian-bases skills for formats) | `scibooster/obsidian.py` |
| Dev renderer (no LLM calls; RAG was removed on purpose, don't re-add) | `renderer/server.py`, `renderer/static/` |

## Extending safely

- New LLM call → add the prompt to `prompts.py`, give it a distinct `purpose=` string, and teach `FakeLLM` in `tests/conftest.py` to answer that purpose, otherwise tests hit the fallback.
- New data source → mirror `sources/openalex.py`: return `Paper` objects, route HTTP through `sources/cache.py`, add a fixture under `tests/fixtures/` and a respx/fake-backed test.
- Schema change in `models.py` → old corpora under `corpora/` must still `Corpus.model_validate`; give new fields defaults.
- New `origin` value → also add it to `_ORIGIN_RANK` (`store.py`) and `ORIGIN` + a `--o-*` colour token (`renderer/static/`).
- New paper property → add it to `_paper_note` frontmatter and, if useful, a Base column in `_base_file`; never write below `NOTES_MARKER` (user-owned).
- PRISMA counts are derived from final pool state in `_fill_prisma`; keep the identity `identified = screened + not_screened + seeds` (tests check it).
- Finish with `pytest -q` green and update `PROGRESS.md` (Chinese) if behaviour or open items changed.

## Related vendored skills

`paper-lookup` (18 scholarly APIs incl. OpenCitations / Semantic Scholar), `paper-search-pro` (RCS rubric, saturation stop rule, PRISMA-S), `citation-management` (DOI→BibTeX, citation validation), `literature-review`, `networkx`, `typer`, `fastapi`. Provenance: `.claude/skills/SOURCES.md`.
