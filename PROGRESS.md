# SCIBooster 工作记录与进展

> 最后更新：2026-10-07　｜　当前阶段：**v0.3**：结果输出为 Obsidian vault，自带渲染器只作开发用途（离线 fCoSE 网状布局，Canvas 共用）。v0.2 已移除 RAG，加入共被引补缺、自适应停止、召回评估、导出、档位、PRISMA 和撤稿过滤。WoS Starter 已用真实 key 跑通。测试分为 `tests/unit/`（管线各环节）和 `tests/cases/`（两个真实案例）。

实现细节与历史改动以 Git 记录和 `README.md` 为准；本文件只记录环境、决策、实测结论和待办。

## 1. 环境

- macOS（Darwin 25.3），Python 3.14.8，虚拟环境 `.venv/`，用 pip 安装：`.venv/bin/pip install -e ".[dev]"`。Node.js 22+ 用于布局测试和 Canvas 布局（本机 v26.10.0）
- 前端库打包在 `renderer/static/vendor/`，渲染器不需要联网，也不需要 npm；升级步骤见该目录 README
- GitHub：私有仓库 https://github.com/LuoxingTshe/SCIBooster 。CI 在 `ubuntu-26.04` 上用 Python 3.11 / 3.14 跑离线测试，另用 Node 22 跑布局测试；push 和 PR 都会触发

`.env`（已加入 .gitignore，权限 600；pydantic-settings 自动读取，key 只需配置一次）：

| 变量 | 状态 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | ✅ | 只存在 `.env` 中 |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | `https://api.deepseek.com` / `deepseek-chat` | |
| `WOS_API_KEY` | ✅ | `build` 默认走 WoS；配额 5000 次/天、5 次/秒 |
| `WOS_MAX_REQUESTS` / `WOS_MIN_INTERVAL` | `60` / `1.1` 秒 | 单次运行的 WoS 请求上限（命中缓存不计） |
| `OPENALEX_EMAIL` / `OPENALEX_API_KEY` | 空 | 可选，填邮箱可进入 polite pool |
| `SCIB_CACHE_DIR` | `.cache` | HTTP 缓存（sqlite），重跑不消耗配额 |
| `SCIB_OBSIDIAN_VAULT` | 空 | 设置后写入 `<vault>/SCIBooster/<run>/`，否则写到 `<run>/obsidian/` |

**必须在项目根目录运行**：`config.py` 按当前目录查找 `.env`。2026-10-05 与用户确认保持现状。

```bash
.venv/bin/scibooster intent "<需求>"                                 # 只解析意图和检索式，便宜
.venv/bin/scibooster build  "<需求>" -s <DOI|标题> --source wos|openalex --tier quick|standard|deep [--label-edges]
.venv/bin/scibooster agent  "<补充方向>" --corpus corpora/<run>/corpus.json --max-steps 30 --max-papers 100
.venv/bin/scibooster eval|export|stats|traverse|obsidian|serve corpora/<run>/corpus.json ...
.venv/bin/python -m pytest -q                       # 66 项离线测试（unit + cases）
node --test tests/unit/test_network_layout.cjs      # 8 项布局测试
.venv/bin/python -m scripts.real_search plan|run|evaluate          # 案例：classical-garden
.venv/bin/python -m scripts.timeline_retrieval plan|run|compare    # 案例：timeline-study 检索复现（默认冻结意图）
.venv/bin/python -m scripts.timeline_variance run|analyze          # 复用缓存，量化 LLM 波动
```

## 2. 关键设计决策（与用户确认过的）

- 日常阅读的输出用 **Obsidian**：每篇文献一条笔记，加上 Base 文献表和 Canvas 引用图谱。渲染器只作开发工具，功能是引用网络可视化和 BFS/DFS 遍历；RAG 已于 2026-10-05 删除，不再加回
- 渲染器与 Canvas 统一使用**宽松的 fCoSE 网状布局**（2026-10-06）。位置只由引用关系决定，年份只出现在标签和筛选里
- `corpus.json` 是唯一的数据源，Obsidian 文件、eval、export、agent 续跑都从它生成或读取
- WoS 使用 Starter API，不提供参考文献，所以**引用边和摘要全部来自 OpenAlex**（按 DOI 匹配）
- 控制流以确定性 pipeline 为默认，可选 DeepSeek tool-calling Agent；Agent 的 `--max-papers` 是硬上限
- 召回评估以已发表综述的参考文献列表作为标准答案（参考 PaSa）
- 真实案例冻结检索式、参数和基线；核对集只在检索结束后读取。`timeline_retrieval run` **默认冻结研究意图**（2026-10-07），`--reparse-intent` 恢复由 LLM 重新解析

## 3. 实测结论

| 日期 | 运行（`corpora/`） | 结论 |
|---|---|---|
| 10-05 | `gnn-drug-quick` / `gnn-drug-wos2` | quick 档 48 篇 / 152 条边，约 20K tokens。WoS 修复了缩写截词（`strip_acronym_truncation`）、检索式之间重复、翻页偏移三个问题 |
| 10-06 | `landscape-planning-history` | 无种子也能运行。发现向前滚雪球得到的文献并不前沿：各环节都按被引数截断。另有同一作品多条 OpenAlex 记录未合并 |
| 10-06 | `real-test-classical-garden-*`、`garden-v1-*` | 古典园林核对集：加四分支后非种子 6/7；固定入口首次重跑 5/7，判为 regression（详见 README） |
| 10-07 | `timeline-repro-2026-10-07` | 用 2026-10-07 原检索的检索式与参数重跑：WoS 命中与原来相同，79 篇候选找回 61 篇（77%），管线找到的直接支持 DOI 命中 18/20 |
| 10-07 | `timeline-variance-2026-10-07` | 冻结意图、复用缓存、重复 3 次：直接支持 DOI 每次都是 20/20。最终语料两两 Jaccard：history 70%，formal_methods 83%。剩余波动来自 5↔6 分的边界评分，以及只取前 3 篇作为滚雪球起点带来的放大 |

**已否决的尝试**（2026-10-07）：对阈值附近的文献多次打分取中位数，没有降低波动（history Jaccard 70%→66%），token 却增加约 90%，代码已回滚。多次打分加起点 6 篇时 Jaccard 为 77% / 87%，但在 3 次重复的噪声范围内，未采纳。摘要见 `tests/cases/timeline-study/retrieval/README.md`。

## 4. 待办 / 待决

- [ ] **待用户决定**：向前滚雪球得到的文献不前沿。可选：① 用 `agent` 或 `--years 2020-2025 --direction forward` 另补；② 前向改为按新近程度或年均被引排序（会改变默认行为）
- [ ] 排查去重：同一作品存在多条 OpenAlex 记录时没有合并，例如 Granite Garden 的两条记录；“Analytic / Analytical hierarchy process” 疑似同类（`store.py`）
- [ ] 可选：timeline 案例单独测试滚雪球起点 `frontier_size` 6，重复 5 次以上；采用的话需另立案例版本
- [ ] 可选：timeline 复现是否设置重合率门槛（目前只检查种子、检索式、重复）
- [ ] 找一篇与需求更贴近的综述作为 `eval` 标准答案，用来比较三个档位
- [ ] **待用户在 Obsidian 中确认**：Base 的 5 个视图及 `sort` 是否生效、总览.md 的 mermaid PRISMA 图、网状 Canvas 的观感、Graph view 着色
- [ ] 安全：DeepSeek / WoS key 曾以明文出现在对话中；如对话会外传，到各自控制台换 key
- [ ] 可选：填写 `OPENALEX_EMAIL`

## 5. 其他备注

- Obsidian 1.13.7 已安装，`corpora/gnn-drug-quick/obsidian/` 已登记为 vault。自带的 `obsidian` 命令行需要在设置中启用（尚未启用）。重新导出时，笔记 `%% scibooster:notes … %%` 以下的用户内容会保留
- `serve` 的默认端口 8765 如果被占用会以 exit 3 退出，可用 `--port` 换端口
- 项目级 skill 在 `.claude/skills/`，来源见 `SOURCES.md`。v0.2 参考外部项目做的改动（补缺、硬上限、召回评估、评分细则、自适应停止、导出、档位、PRISMA、撤稿过滤）见 Git 记录与 README
