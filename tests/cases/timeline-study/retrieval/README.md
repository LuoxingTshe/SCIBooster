# TimelineStudy 检索复现

本目录只用于复现 2026-10-07 的 SCIBooster 检索步骤：两条分支各跑一次 `build_corpus`，结果与当时的 79 条候选比较。DOI 身份核验、Crossref 审计、直接支持清单的筛选和时间线重构都不在复现范围内。上一级目录的案例文件与 `cases/timeline-study/` 逐字节相同（`SOURCE_MANIFEST.json` 的哈希由测试检查）。

|文件|用途|
|---|---|
|`case.json`|两条分支的研究意图、种子、三条固定 WoS 检索式和完整 `BuildParams`；模型 deepseek-chat，温度 0.2，每分支 WoS 请求上限 25|
|`baseline/history.corpus.json`、`baseline/formal_methods.corpus.json`|原始运行的语料（21 + 58 = 79 篇），取自 EssayI `research/runs/2026-10-07-scibooster/`|
|`baseline/source-protocol.json`|原始运行的 protocol.json，原样复制|
|`runs.json`|基线与各次复现的摘要|

```bash
.venv/bin/python -m scripts.timeline_retrieval plan                       # 离线：显示种子和实际检索式
.venv/bin/python -m scripts.timeline_retrieval run --out corpora/timeline-repro-<label>   # 真实 API，约 22 次 DeepSeek 调用、6 次 WoS 请求
.venv/bin/python -m scripts.timeline_retrieval compare corpora/timeline-repro-<label>     # 离线重算对比
```

`run` 的每条分支使用独立的新 HTTP 缓存，输出目录必须不存在，结果写入 `comparison.md` / `comparison.json`。只有结构问题会导致非零退出码：种子未全部解析、实际检索式与 `case.json` 不同、语料内重复。重合率只用于描述，不作为通过门槛。

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
