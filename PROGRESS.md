# SCIBooster 工作记录与进展

> 最后更新：2026-10-06　｜　当前阶段：**v0.3：结果输出为 Obsidian vault（自带渲染器降级为开发工具，2026-10-06 改为离线 fCoSE 网状布局，Obsidian Canvas 同步改用该布局）；v0.2 已移除 RAG 并新增补缺 / 自适应停止 / 召回评估 / 导出 / 档位 / PRISMA / 撤稿过滤；WoS Starter 已用真实 key 跑通（2026-10-05）**

## 1. 环境与启动项

### 运行环境
- macOS（Darwin 25.3），Python **3.14.8**，虚拟环境 `.venv/`（未使用 uv，用的是 pip）
- 主要依赖版本：openai 3.24.0 · pyalex 0.21 · httpx 0.28.1 · pydantic 2.13.5 · pydantic-settings 2.15.0 · networkx 3.7 · rank-bm25 0.2.2 · tenacity 9.1.4 · typer 0.27.2 · rich 15.0.0 · fastapi 0.142.2 · uvicorn 0.54.0 · pytest 9.1.1 · respx 0.23.1
- 前端库已打包到 `renderer/static/vendor/`（2026-10-06，附 LICENSE）：cytoscape 3.30.4、layout-base 2.0.1、cose-base 2.2.0、cytoscape-fcose 2.2.0，**渲染器无需联网，也不需要 npm**；升级步骤见 `renderer/static/vendor/README.md`。dagre / cytoscape-dagre 已移除
- 布局回归测试用 Node.js 22+ 自带的 `node:test` 运行（本机 Node v26.10.0）

### 首次安装 / 重建环境
```bash
cd /Users/xie/code/SCIBooster
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env    # 填写 key
```

### 环境变量（`.env`，已加入 .gitignore，权限 600）
| 变量 | 当前状态 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | ✅ 已设置 | 明文只存在 `.env` 中，不写入任何其他文件 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 可换成其他 DeepSeek 模型 |
| `WOS_API_KEY` | ✅ 已设置（2026-10-05） | `build` 默认走 WoS。实测配额：**5000 次/天、5 次/秒**（见响应头 `x-ratelimit-*`） |
| `WOS_MAX_REQUESTS` | `60` | 单次运行的 WoS 请求上限，命中缓存不计（2026-10-05 由 20 调到 60，deep 档最多需要约 24 次） |
| `WOS_MIN_INTERVAL` | `1.1` | WoS 两次请求之间的最小间隔（秒） |
| `OPENALEX_EMAIL` / `OPENALEX_API_KEY` | 空 | 可选；填写邮箱可进入 OpenAlex 的 polite pool（限流更宽松） |
| `SCIB_CACHE_DIR` | `.cache` | HTTP 缓存目录（sqlite，目前约 22MB），重跑同一任务不消耗配额 |
| `SCIB_OBSIDIAN_VAULT` | 空 | 已有的 Obsidian vault 路径；设置后每次运行写入 `<vault>/SCIBooster/<run>/`，留空则写到 `<run>/obsidian/`（可以直接作为 vault 打开） |

> **key 只需配置一次**：每次运行时，程序（pydantic-settings）都会自动读取 `.env`，不需要再输入 key，也不需要手动 export 环境变量。以后拿到 WoS key，同样只需在 `.env` 里填一次 `WOS_API_KEY=...`。
>
> **限制：必须在项目根目录下运行**。`config.py` 中写的是 `env_file=".env"`，按"当前所在目录"查找。在其他目录下用完整路径调用 `scibooster`，会因为找不到 `.env` 而报 `DEEPSEEK_API_KEY is not set`。
> 2026-10-05 已与用户确认：**保持现状，不改成固定指向项目根目录**。

### 常用启动命令
```bash
cd /Users/xie/code/SCIBooster
.venv/bin/scibooster intent "<研究需求>"                         # 只解析意图、生成检索式，便宜，适合调试
.venv/bin/scibooster build  "<研究需求>" -s <DOI或标题> --source openalex --tier quick|standard|deep --label-edges
.venv/bin/scibooster agent  "<补充方向>" --corpus corpora/<run>/corpus.json --max-steps 30 --max-papers 100   # 硬上限
.venv/bin/scibooster eval     corpora/<run>/corpus.json --gold <综述 DOI>   # 召回率，写 eval.json，不调用 LLM
.venv/bin/scibooster export   corpora/<run>/corpus.json -f bibtex|ris|csv --min-score 7
.venv/bin/scibooster stats    corpora/<run>/corpus.json
.venv/bin/scibooster traverse corpora/<run>/corpus.json --start <W-id> --mode dfs --direction cited_by
.venv/bin/scibooster obsidian corpora/<run>/corpus.json [--vault ~/某个vault]   # build/agent 跑完会自动生成
.venv/bin/scibooster serve    corpora/<run>/corpus.json          # 开发用渲染器 → http://127.0.0.1:8765
.venv/bin/python -m pytest -q                                     # 44 项测试
node --test tests/test_network_layout.cjs                         # 8 项布局测试（Node 22+）
```

## 2. 实测记录（2026-10-05，真实 DeepSeek + OpenAlex）

示例语料库位于 `corpora/gnn-drug-demo/`：
- `corpus.json`：由 pipeline 生成
- `corpus.agent.json`：在 corpus.json 基础上经 Agent 扩充
- `trace.jsonl`：每一次调用的记录

| 步骤 | 命令要点 | 结果 |
|---|---|---|
| 意图解析 | `intent "图神经网络在药物发现中的应用，重点关注分子性质预测和药物-靶点相互作用" --years 2017-2025` | 3 个概念面 + 同义词，生成 3 条合法的 WoS 检索式；2 次调用，约 1.7K tokens |
| 构建语料库 | `build ... -s 10.48550/arXiv.1704.01212 -s "Analyzing Learned Molecular Representations for Property Prediction" --source openalex --per-query 40 --per-node 15 --frontier 8 --prefilter 100 --max-papers 60 --label-edges` | 60 篇文献 / 196 条引用边（其中 150 条带语义标注）；耗时 42 秒；32 次调用，约 78K tokens |
| Agent | `agent "补充 2023 年以后基于预训练/大模型的分子性质预测工作" --max-steps 8 --max-papers 75` | 工具调用正常；语料库从 60 篇扩到 89 篇，并自动写出总结和尚未覆盖的方向（当时上限只是建议值，现已改为硬上限） |

v0.2 实测（2026-10-05，`corpora/gnn-drug-quick/`，同一需求与种子，`--tier quick --years 2017-2025`）：
- 48 篇 / 152 条边；6 次 DeepSeek 调用，约 20K tokens，耗时约 14 秒
- 共被引补缺：15 篇缺失文献中取回 13 篇，6 篇相关并纳入（MoleculeNet、GraphDTA、PotentialNet 等）；MoleculeNet 成为库内被引最多的文献（23 次）
- PRISMA：识别 72（种子 2 + 检索 57 + 补缺 13，检索重复命中 3）→ 筛选 70 → 排除 24 → 纳入 48
- `eval --gold 10.1016/j.ddtec.2020.11.009`（Wieder 2020 综述，72 篇参考文献）：新语料召回 8.3%（6/72）；旧 demo 的 corpus.json 和 corpus.agent.json 都是 4.2%（3/72）。该综述引用了大量通用 GNN 文献，所以绝对值偏低，只适合用来横向比较
- `export` 三种格式都能导出；旧语料（没有 prisma / retracted 字段）仍可正常加载

WoS 实测（2026-10-05，真实 WoS Starter + OpenAlex，同一需求与种子，`--source wos --tier quick --years 2017-2025`）：
- 最小请求验证：200；`parse_hit` 解析出的 DOI / 年份 / 期刊 / WoS 被引数都正确；WoS 命中 100% 能按 DOI 映射到 OpenAlex（引用边、摘要齐全）
- 发现问题 1：LLM 会写出 `"GAT*"` 这类短缩写截词，在 WoS 中会匹配 gate / gather（同条件下 947 篇对比 52 篇）→ prompt 增加规则，并在 `pipeline/query.py` 中新增确定性清洗函数 `strip_acronym_truncation`
- 发现问题 2：每条检索式都按被引数降序取前 N 条，彼此高度重叠（60 条命中中重复 26 条）→ `per_query` 改为只统计**新增不重复**文献，后面的检索式会往后翻页（每条最多读 3×per_query 条）
- 发现问题 3（旧 bug）：`search_all` 最后一页用剩余条数作为 `limit`，而 WoS 的偏移量按 `(page-1)×limit` 计算，导致翻页取错位置 → 翻页过程中固定页大小
- 结果：`corpora/gnn-drug-wos/`（修复前）29 篇 / 97 条边；`corpora/gnn-drug-wos2/`（修复后）47 篇 / 186 条边，WoS 仅用 2 次请求，DeepSeek 7 次调用，约 21K tokens
- `eval --gold 10.1016/j.ddtec.2020.11.009`：openalex quick 8.3%（6/72，47 篇）· wos 修复前 9.7%（7/72，29 篇）· wos 修复后 8.3%（6/72，47 篇）。每次运行时 LLM 都会重新生成检索式，加上这篇综述不太贴合需求，差异属于噪声范围

## 3. 关键设计决策（与用户确认过的）
- 渲染器 = **引用网络可视化 + BFS/DFS 遍历**（2026-10-05 用户决定删除 RAG 问答，并取消 RAG 相关的待办；渲染器不再调用 LLM）
- 2026-10-06 用户（借助多模态模型）重写渲染器布局：**去掉按年代分层 DAG / dagre 拓扑分层 / 时间轴 / 旧力导向四种布局，统一改为宽松的 fCoSE 力导向网状布局**（`renderer/static/network-layout.js`）。位置只由引用关系决定，年份只出现在节点标签和筛选里，不作位置约束；按年份分层的视图留给 Obsidian Canvas
- 2026-10-05 用户决定：**日常阅读的输出改为 Obsidian 格式**，自带渲染器只作开发用途。Obsidian 自带的 Graph view 只有力导向布局，不支持边标签、边颜色和分层，所以引用 DAG 用 Canvas（JSON Canvas 1.0）表达；文献表用 Bases（需要 1.9 及以上）；每篇文献一条笔记（properties + 类型化引用链接）
- `corpus.json` 仍是唯一的数据源（eval / export / agent 续跑 / 开发渲染器都读它），Obsidian 文件由它生成
- WoS 使用 **Starter API**：它不提供参考文献数据，所以**引用边和摘要全部来自 OpenAlex**（按 DOI 匹配）
- 控制流 = **确定性 pipeline（默认）+ 可选的 DeepSeek tool-calling Agent**
- Agent 的 `--max-papers` 为**硬上限**：在 `add_to_corpus` 中强制执行，超出时拒绝并提示先移除或 finish
- 召回评估以已发表综述的参考文献列表作为标准答案（参考 PaSa 的 recall@k 评估）

## 4. 实现过程中发现并处理的问题
- 有些 arXiv DOI 在 OpenAlex 里查不到 → 改为通过 doi.org 内容协商拿到标题，再按标题匹配
- OpenAlex 的年份有时不准（如《Attention Is All You Need》被记成 2025 年）→ 按标题匹配时不加年份过滤，取相似度 ≥0.9 的候选中被引最多的一条
- 检索结果与种子文献重复时，WoS 字段没有合并进种子 → 已修复（有测试覆盖）
- 合并记录时 WOS id 升级为 OpenAlex id 后索引失效 → 已修复
- dagre 布局在稠密图上被压得很扁 → 新增"按年代分层"布局作为默认（按年份分行，行内用重心法排序以减少边交叉）
- 2026-10-06：渲染器整体换成 fCoSE 网状布局：`quality: "proof"` + `nodeDimensionsIncludeLabels`，模拟结束后按包含标签的包围盒做一次**等比例放大**（`separateBounds`，不改变角度和边交叉数）以消除重叠；三档间距（舒展 / 宽松 / 更宽松）、重新布局、适应画布、展开画布（隐藏右栏）；悬停或选中文献时只突出其直接引用、其余淡化，点空白处或「取消聚焦」恢复；BFS/DFS 回放时不叠加邻域高亮；fCoSE 不可用时退回内置 CoSE。详情面板里指向被筛掉文献的链接不再移动画布，只显示详情
- 测试：`tests/test_renderer.py` 新增断言——页面引用的 `<script>` 必须全部来自 `/static/` 且可访问（防止回退到 CDN）；`tests/test_network_layout.cjs` 在 `vm` 中直接执行打包的浏览器脚本，覆盖无重叠、年份不影响位置、筛选、空图/孤立点/不连通图、间距档位和 CoSE 回退。CI 增加 Node 22 步骤；`pyproject.toml` 的 package-data 加入 `static/vendor/*`
- v0.2：导出与前端都用 `startswith("W")` 判断 OpenAlex id，导致 `WOS:` 开头的 id 被误当成 OpenAlex id → 改为匹配 `^W\d+$`（有测试覆盖）

## 5. 待办 / 待决
- [x] **接入 WoS Starter key**，用真实 WoS 跑通（2026-10-05，见 §2「WoS 实测」）
- [ ] 安全：WoS key 也以明文出现在对话中，如对话会外传，建议在 Clarivate 开发者门户重新生成
- [x] Agent 的 `--max-papers` 改为硬上限（v0.2）
- [ ] 安全：DeepSeek key 曾以明文出现在对话中，如对话会外传，建议到控制台换 key
- [ ] 可选：填写 `OPENALEX_EMAIL`
- [x] 前端库本地化、渲染器可离线使用（2026-10-06，见 §4）
- [x] Node 布局测试步骤在 GitHub Actions 上通过（2026-10-06 手动触发的 run 37438958446，提交 a97752f）。当时 push 仍未自动触发 CI
- [x] 2026-10-06 CI 升级：actions/checkout、setup-python、setup-node 均升到 v7（Node 24 运行时，消除 Node 20 弃用警告），runner 固定为 `ubuntu-26.04`（`ubuntu-latest` 从 2026-10-19 起切到 26.04，提前固定可以验证兼容性）；Node 仍测 22（README 写明的最低版本）。之后 push 到分支和 main 都能自动触发 CI，并在 3.11 / 3.14 上通过（run 37439281592），之前不触发的原因没有查明
- [x] `git init` 已完成（v0.2），2026-10-05 完成首次提交（main）；`.github/workflows/ci.yml` 会在 Python 3.11 和 3.14 上跑离线测试。2026-10-05 已推送到私有仓库 https://github.com/LuoxingTshe/SCIBooster；手动触发的 CI（workflow_dispatch）在 3.11 和 3.14 上均通过，但两次 push 都没有自动触发 CI，原因待查
- [ ] 建议找一篇与需求更贴近的综述作为 `eval` 的标准答案，用它来比较 quick / standard / deep 三个档位
- ~~RAG 相关待办（中文提问检索、证据式问答、embedding 检索）~~：已随 RAG 一并取消

## 6. Obsidian 输出（v0.3，2026-10-05）
- 实测：`scibooster obsidian corpora/gnn-drug-quick/corpus.json` → 48 篇笔记 + 文献库.base + 引用图谱.canvas（当时为 10 个年份分组、152 条边，约 3280×3380 px；2026-10-06 已改为网状布局）+ 总览.md；用 PyYAML / JSON 解析器校验，48 份 frontmatter 和 .base 均无错误，边全部指向存在的节点
- 2026-10-05 已通过 `brew install --cask obsidian` 安装 Obsidian 1.13.7，并把 `corpora/gnn-drug-quick/obsidian/` 登记为 vault 打开（为此改过 `~/Library/Application Support/obsidian/obsidian.json`，原有条目未动）。Obsidian 首次启动时还自动建了默认 vault `~/Documents/Obsidian Vault`，用户可以自行删除
- [ ] **待用户在 Obsidian 中确认**：① ~~引用图谱.canvas 的分层、颜色、观感~~（已改为网状布局，见下方 2026-10-06）；② 文献库.base 的 5 个视图，以及 `sort`（按社区示例写的，官方文档没有说明）是否生效；③ 总览.md 的 mermaid PRISMA 图和嵌入的文献表
- Obsidian 自带的命令行工具 `obsidian` 需要 Obsidian 正在运行，并在 设置 → 通用 里启用后才能用（尚未启用）
- 重新导出时，笔记中 `%% scibooster:notes … %%` 标记以下的用户内容会保留；Canvas 和 Base 每次整体重新生成
- 新增 skill：`obsidian-markdown` / `obsidian-bases` / `json-canvas`（kepano/obsidian-skills，MIT）

### 2026-10-06：Canvas 改用渲染器的网状布局
- 用户要求"利用现有渲染器的渲染逻辑，参考 GitHub 上成熟方案，更新 Obsidian 导出"。实现：
  - 新增 `renderer/layout.cjs`：在 Node 的 `vm` 中加载打包好的 cytoscape + fCoSE 和 `network-layout.js`，无头运行 `NetworkLayout.run`，stdin 输入图、stdout 输出坐标；随机数固定种子（42），重新导出结果完全一致。Node 测试也改为复用它的加载函数
  - `obsidian.py`：`引用图谱.canvas` 不再按年份分组，卡片（320×150）坐标来自上述布局；边按两张卡片的相对位置选择出入的边；新增"图例"分组（来源颜色、关系边颜色、箭头方向）。节点颜色改用渲染器的 `--o-*` 色值，三处配色一致。没有 Node 时退回 networkx spring 布局 + Python 版 `separate_bounds`，CLI 会提示
  - 新增 `.obsidian/graph.json` 配色组（撤稿 → 种子 → 各来源，按标签匹配），给 Obsidian 自带 Graph view 着色；只替换 `tag:#scibooster/` 开头的组，用户其他设置和配色组保留，无法解析的文件不动；新建时打开箭头。做法参考 graphify（Graphify-Labs/graphify，Apache-2.0/MIT）的 Obsidian 导出，并避开其 #2204 的问题（配色组查询与笔记标签清洗规则不一致导致配色失效）：查询直接使用笔记里写的标签字符串，测试保证每篇笔记都会被某个配色组匹配到
  - 调研过但没有采用：graphify 的 Canvas 按社区排成网格，不反映引用结构；Juggl、Extended Graph、Advanced Canvas 等插件需要用户另装，而 SCIBooster 的输出不依赖任何插件
- 实测：gnn-drug-quick（48 篇 / 152 条边）0.6 秒，Canvas 约 6400×4200 px；gnn-drug-demo（60 篇）约 7900×5300 px；合成的 400 篇图约 12 秒（超时上限 120 秒）
- 已用新版本重新导出 `corpora/gnn-drug-quick/obsidian/`（导出时 Obsidian 正在运行；graph.json 是新建的，如果看不到着色，重新打开该 vault）
- [ ] **待用户在 Obsidian 中确认**：网状 Canvas 的观感（卡片间距、边的出入方向、图例），以及 Graph view 的着色

## 7. Claude Code skill 配置（2026-10-05）
项目级 skill 安装在 `.claude/skills/`，来源与 commit 见 `.claude/skills/SOURCES.md`：
- `scibooster`：本项目专用（启动命令、不变量、扩展约定）
- `paper-lookup` / `citation-management` / `literature-review` / `networkx`：K-Dense-AI/scientific-agent-skills（MIT）
- `paper-search-pro`：O0000-code/paper-search-pro（Apache-2.0；RCS 评分细则、饱和停止规则、PRISMA-S）
- `typer` / `fastapi`：随 .venv 中的包附带的官方 skill
- `obsidian-markdown` / `obsidian-bases` / `json-canvas`：kepano/obsidian-skills（MIT），用于 Obsidian 输出

对照 GitHub 高星项目审查后，v0.2 落实的修改：
| 修改 | 参考项目 | 位置 |
|---|---|---|
| 共被引补缺（build 第 6 步 + Agent 工具 `top_missing_refs`） | LocalCitationNetwork | `pipeline/gaps.py` |
| Agent `--max-papers` 硬上限 | open_deep_research、PaSa | `agent/tools.py` `t_add` |
| 召回评估 `scibooster eval` | PaSa | `evaluate.py` |
| 带锚点的 0–10 评分细则；无摘要文献标记 `no_abstract` | paper-search-pro | `llm/prompts.py`、`pipeline/screen.py` |
| 自适应停止：某一跳的相关占比低于 `--min-hop-yield` 就停止 | ASReview、paper-search-pro | `pipeline/build.py` |
| 导出 BibTeX / RIS / CSV | citation-management | `export.py` |
| 档位预设 `--tier` | paper-search-pro | `pipeline/build.py` `TIERS` |
| PRISMA 流程记录（`meta.prisma`），stats 与渲染器中展示 | paper-search-pro | `models.py`、`renderer/static/app.js` |
| 撤稿标记与过滤（OpenAlex `is_retracted`） | paper-qa | `sources/openalex.py` |
| git + CI | — | `.github/workflows/ci.yml` |
