# TimelineStudy 检索复现

本目录只用于复现 2026-10-07 的 SCIBooster 检索步骤：两条分支各跑一次 `build_corpus`，结果与当时的 79 条候选比较。DOI 身份核验、Crossref 审计、直接支持清单的筛选和时间线重构都不在复现范围内。文献包位于上一级 `literature/`，保留内容由 `SOURCE_MANIFEST.json` 哈希检查；非检索研究产物已移出测试目录。

|文件|用途|
|---|---|
|`case.json`|两条分支的研究意图、种子、三条固定 WoS 检索式和完整 `BuildParams`；模型 deepseek-chat，温度 0.2，每分支 WoS 请求上限 25|
|`baseline/history.corpus.json`、`baseline/formal_methods.corpus.json`|原始运行的语料（21 + 58 = 79 篇），取自 EssayI `research/runs/2026-10-07-scibooster/`|
|`baseline/source-protocol.json`|原始运行的 protocol.json，原样复制|
|`runs.json`|基线与各次复现的摘要|

```bash
.venv/bin/python -m scripts.timeline_retrieval plan                       # 离线：显示种子和实际检索式
.venv/bin/python -m scripts.timeline_retrieval run --out artifacts/runs/timeline-repro-<label> --keep-history --keep-cache   # 真实 API，并保留缓存供下一条波动实验复用
.venv/bin/python -m scripts.timeline_retrieval run --out ... --reparse-intent               # 让 LLM 重新解析意图（repro-1 的做法）
.venv/bin/python -m scripts.timeline_variance run --out artifacts/runs/timeline-variance-<label> --cache-from artifacts/runs/timeline-repro-<label> [--set frontier_size=6]   # 复用缓存，只量化 LLM 波动
.venv/bin/python -m scripts.timeline_retrieval compare artifacts/runs/timeline-repro-<label>     # 离线重算对比
```

`run` 默认**冻结研究意图**：直接使用基线语料 `meta.intent` 中记录的意图，不再调用 LLM 重新解析（2026-10-07 实验表明意图重解析是最大的波动来源）。每条分支使用独立的新 HTTP 缓存，输出目录必须不存在，结果写入 `comparison.md` / `comparison.json`。只有结构问题会导致非零退出码：种子未全部解析、实际检索式与 `case.json` 不同、语料内重复。重合率只用于描述，不作为通过门槛。

通过后默认清空缓存并删除先前完成的受管理结果，失败保留旧结果与缓存。
需要跨次对比或继续波动实验时加 `--keep-history --keep-cache`。
波动实验的所有重复作为一份完整结果，在实验结束后统一清理；源语料副本保存在
本次 `inputs/` 中，因此原运行被删除后仍能离线 `analyze`。

## 比较口径

- 文献按 DOI 归一化后匹配；没有 DOI 的按 OpenAlex id 匹配，再不行按题名匹配。
- “直接支持记录（管线发现部分）”：`direct_support_doi.json` 的 41 条中，DOI 出现在 79 条候选里的有 20 条（种子 9 条，非种子 11 条）。其余 21 条来自定向 DOI/题名核对，不属于检索。
- 相关度分数来自实时模型，WoS/OpenAlex 的索引也会变化。重合率反映的是复现程度，不代表检索质量或事实支持。

## 第一次复现（repro-1，2026-10-07）

检索式与参数相同，WoS 新候选数与基线一致（history 70 条，formal_methods 103 条）。

|分支|基线|本次|重合|基线覆盖|
|---|---|---|---|---|
|history|21|13|12|57.1%|
|formal_methods|58|52|49|84.5%|
|合计|79|65|61|77.2%|

管线发现的直接支持记录命中 18/20，非种子 9/11；未命中的是 DS004（Tyrwhitt 1941–1951）和 DS018（Saaty 1977）。基线中缺失的 18 篇在基线里都是 6–7 分，多数恰在阈值 6。两次运行的 DeepSeek 意图解析得到的概念面不同。因此差异主要来自 LLM 的意图解析和边界评分，不是 WoS 返回结果变了。history 分支纳入的文献少，边界上的波动对它影响更大。

## 波动实验（2026-10-07）

冻结基线意图，复用 repro-1 的 HTTP 缓存（WoS 0 次实时请求），每组重复 3 次，只剩 DeepSeek 打分在变。最终语料两两 Jaccard 和稳定核心（3 次都入选 / 3 次合计）：

|配置|history|formal_methods|DeepSeek token（每次两分支）|
|---|---|---|---|
|冻结意图|70%（15/26）|83%（48/63）|约 6 万|
|A：+ 阈值附近多次打分取中位数|66%（15/28）|85%（44/56）|约 11 万|
|B：A + 滚雪球起点 6 篇|77%（19/28）|87%（49/60）|约 11 万|

冻结意图后，管线找到的 20 条直接支持 DOI 在 3 次中都全部命中（repro-1 为 18/20）。A 没有减少跨阈值的翻转，多次打分的代码已回滚；B 的小幅提升在 3 次重复的噪声范围内，未改动冻结协议。本地仅保留 `artifacts/runs/timeline-variance-2026-10-07`（冻结意图组）；A、B 两组原始数据已删除，以上表格为其摘要。
