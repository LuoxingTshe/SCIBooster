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
                        "excluded_over_cap": 0, "excluded_out_of_year": 0, "included": 48,
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
tests/                   see tests/README.md
  unit/                  per-stage offline tests (fake LLM + in-memory citation universe + respx-mocked WoS)
    test_network_layout.cjs  node:test layout regression suite
  cases/                 frozen real-search cases: classical-garden (current tech), timeline-study (history)
```

## Tests

```bash
.venv/bin/python -m pytest -q
node --test tests/unit/test_network_layout.cjs  # offline layout regression tests; Node.js 22+
# tests/unit/test_obsidian.py also runs the Canvas layout through Node when it is installed, and always tests the fallback
```

CI (`.github/workflows/ci.yml`, `ubuntu-26.04`, actions v7 on the Node 24 runtime) runs the Python suite on Python 3.11 and 3.14, plus the layout tests on Node.js 22. Layout tests execute the bundled browser scripts and cover overlap, year independence, filtering, empty/disconnected graphs, spacing, the fallback layout and the headless `layout.cjs` entry point (Canvas-sized cards, reproducibility, CLI).

## 本次改动与真实测试（2026-10-06）

围绕人工提供的古典园林文献包，完成了两轮真实 DeepSeek + WoS + OpenAlex 测试，并作出以下改动：

- 核心文献固定为 3 篇：皇家园林三维保护、历史园林点云空间分析、古典园林假山定量分析。
- `build --branch` 可重复指定四个额外 WoS 分支：`vegetation_tls`（古树植被/TLS）、`garden_syntax`（园路/空间句法）、`garden_reviews`（园林综述）、`heritage_pointcloud`（遗产点云方法）。不指定分支时保留原有通用检索行为。这四个分支是本领域的显式选项，并非所有研究主题通用的查询。
- `build` 对检索补全、引文扩展和共引补缺阶段的已知年份执行显式年份边界，修复初始查询受年份限制而扩展结果越界的问题。`excluded_out_of_year` 记录剔除事件；未知年份及用户显式种子仍按现有规则保留，固定测试会将未知或越界年份判为需关注。
- 整理 `tests/`：离线系统测试放在 `tests/system/`，可提交的真实测试输入移入 `tests/fixtures/real_search/`（2026-10-07 起位于 `tests/cases/classical-garden/`，见 [`tests/README.md`](tests/README.md)），不再依赖 macOS 的 `SCI`/`sci` 大小写兼容。原始 PDF 与约 397 MB 文献包保留本地，不提交 Git；运行结果在 `corpora/`。
- 新增固定测试入口 `python -m scripts.real_search`：锁定研究意图、种子、基础检索式、分支和参数；真实调用生产管线后自动检查语料、导出 Obsidian、核对 DOI、写报告。基准答案只用于运行后的评估，不参与检索或筛选提示。

以下是把两轮已有语料按**同一个十篇核对集**重新计算的结果，机器可读基线见 [`baselines.json`](tests/cases/classical-garden/baselines.json)：

| 指标 | 原始三查询 | 加四分支及年份过滤 |
|---|---:|---:|
| 语料记录数 / 引文边 | 53 / 184 | 66 / 217 |
| 种子命中 | 3/3 | 3/3 |
| 十篇核对集命中（含种子） | 7/10 | 9/10 |
| 七篇非种子独立命中 | 4/7（57.1%） | 6/7（85.7%） |
| 最终已知年份越界 | 9 | 0 |
| DeepSeek / WoS / OpenAlex 请求 | 33 / 4 / 29 | 39 / 9 / 27 |
| 全文献包已核实重合论文数（另一统计口径） | 8 | 9 |

**评估口径更正：**十篇核对集是对话复盘中整理出的子集，并非首次运行前预注册的盲测集；现将其版本化，供后续开发回归。9/10 不是整个 PDF 包的召回率。种子被强制保留且评分为 10，不计入独立召回。人工包包含异质主题、重复文件和范围外论文，未完成全包正负标注；外部新增论文不等于误收，不能用“9/66”推算精确率。两轮的 LLM 主查询及年份过滤也不同，因此不能把差异全部归因于新分支。

新增找回的核对文献是古树/TLS 和语义点云数字孪生；六篇命中的非种子文献模型评分为 7–9。该评分来自检索系统自身，不是独立人工相关度评价。

**固定入口首次验证（同日）：**独立缓存、固定七条查询真实重跑后得到 59 条记录 / 177 条边；三篇种子齐全，核对集 8/10，非种子 5/7（71.4%），年份越界与未知均为 0。园林保护综述和语义点云数字孪生未收录，低于 6/7 门槛，入口正确返回 `regression` / 退出码 1。API 用量为 DeepSeek 36、WoS 9、OpenAlex 40 次。保留原门槛，不把这次回退改写成通过；固定查询仍不能消除意图解析、预筛选、模型评分及数据库变化造成的波动。

## 固定真实测试管线

在项目根目录、完成安装后运行：

```bash
# 只查看锁定的输入和七条查询；不读取密钥，不调用 API
.venv/bin/python -m scripts.real_search plan

# 完整真实运行；需 DEEPSEEK_API_KEY、WOS_API_KEY 及可访问的 OpenAlex
# 每次使用新的目录，避免覆盖语料和日志；会消耗实际 API 配额
.venv/bin/python -m scripts.real_search run --out corpora/garden-v1-dev001

# 离线复评已有语料；不调用 API；报告也必须写入新目录
.venv/bin/python -m scripts.real_search evaluate \
  corpora/real-test-classical-garden-branches-20261006/corpus.json \
  --out corpora/garden-v1-audit001
```

[`case.json`](tests/cases/classical-garden/case.json) 固定 2018–2025、WoS 主检索、3 条基础查询加 4 个分支、每查询 50 条、一跳双向扩展、每节点 25 条、前沿 15、预筛选 150、阈值 6、上限 200、共引至少 3 次且最多 30 条，以及边标注参数。模型固定 `deepseek-chat`、temperature=0.2，单次 WoS 请求预算 60。直接调用通用 CLI 时仍可自由配置；要比较开发版本，请使用固定入口。

每次真实运行使用独立的 HTTP 缓存，保存 `inputs/` 输入快照、`run.json`（Git 提交、工作区状态、代码/输入摘要、模型、实际用量、运行状态）、`console.log`、`trace.jsonl`、`http.sqlite`、`corpus.json`、`obsidian/`、`benchmark.json` 和 `benchmark.md`。失败也保留状态与日志。所有运行产物留在本地，密钥不写入测试配置或 Git。

质量检查要求三篇种子完整、非种子核对文献至少命中 6/7、年份已知且在范围内、记录 ID/DOI 不重复、引用边有效，并检查真实运行是否执行了全部固定查询。通过退出码为 0，召回回退或检查失败为非零。固定输入不保证数据库、模型或索引永远不变；回退应结合报告分析，不能直接等同于代码错误。

普通 CI 只跑离线测试（含管线配置与评估器），不会消费真实 API 配额。真实测试由开发者主动运行。核对集修改必须另立版本并解释理由，不应为提高指标而移除漏检文献；下一阶段应补充独立主题和未参与调整的验证集。

## 当前问题与后续工作

| 优先级 | 问题与已知证据 | 后续处理 |
|---|---|---|
| 高 | 缺少逐篇过程记录。trace 只保存 LLM 调用和 token 用量；未保存筛选输入/响应、BM25 排名、淘汰理由及查询归属。园林保护综述（`10.1186/s40494-024-01483-z`）被综述分支找到，却未收录，第二轮无法精确区分预筛选截断与低分排除。 | 保存候选及逐阶段决策；失败批次与缓存命中也应可追踪。 |
| 高 | 评估范围有限。十篇子集在复盘后确定；尚无全包年份、主题、正负标签，也无独立精确率评价。 | 固定当前回归集；补全人工标注、独立验证集及抽样相关度评价，区分核心、综述、方法参考。 |
| 高 | 截断可能影响召回。第二轮 180 条检索候选只送筛 150 条，303 条扩展候选只送筛 150 条，共 183 条未筛；四分支间共享筛选配额，没有分支保底。 | 分支配额、语义召回/重排与参数消融；目前没有证据把第一轮具体漏项直接归因于 BM25。 |
| 高 | 被引数排序有偏。WoS、前向引用和后向参考均优先高被引，并受每查询/每节点上限及一跳限制影响。 | 比较新近排序、主题覆盖和混合排序，评估低被引新文献及边缘子主题。 |
| 高 | 跨 DOI/OpenAlex ID 的版本未合并。假山定量、三苏祠数字保存及扫描仪比较等出现预印本/正式稿疑似重复。 | 基于版本关系、题名、作者核对同一研究；区分记录数与独立研究数。 |
| 中 | 综述与方法参考的纳入边界不明确。统一单一相关度分数可能低估背景综述，也可能保留过泛的方法综述。 | 明确文献角色、分角色标准，避免只降低全局阈值。 |
| 中 | 年份和文献类型仍有边界。build 已过滤已知越界年份，但未知年份、种子例外、在线年/卷期年差异、agent 模式均需独立处理；扩展阶段未强制执行 Article/Review/Proceedings 类型要求。 | 显式年份政策、缺失年份标记、类型过滤与 agent 一致性检查。 |
| 中 | 共引补缺效率与计数。第二轮取回 30 条但年份过滤后仅 2 条；越界论文移出候选池后可能被后续阶段再次取回。`excluded_out_of_year` 可能跨阶段重复，`identified` 仅统计留在池中的记录，二者不能直接相加为唯一发现量。 | 提前年份筛选、回填有效候选、记录排除 ID 和完整 PRISMA 口径。 |
| 中 | 摘要与标识符不完整；缺摘要保守评分、题名回退预算及 OpenAlex 覆盖均可能影响检索与匹配。 | 记录缺失/解析失败与补全来源；匹配不确定时人工核验。 |
| 中 | 固定模板仅适用于本次园林场景；人工分支不可直接迁移到所有主题。固定入口实测非种子命中从 6/7 回退到 5/7，查询虽固定，意图解析及评分仍可变化。 | 记录逐篇决策，评估重复运行的方差；抽象通用分支配置，加入多领域真实用例，按版本记录提示与模型。 |

已修复并加入回归检查：build 已知年份越界、分支配置在 API 调用前校验、固定查询跳过 LLM 查询生成、种子 WoS 字段合并，以及测试夹具的跨平台路径依赖。其余问题保留在上表，未作为已解决事项。
