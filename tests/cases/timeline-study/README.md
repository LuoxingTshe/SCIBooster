# TimelineStudy：检索回归案例

本案例只维护 SCIBooster 检索测试。输入源于 EssayI 2026-10-07 的书目与 DOI 核验材料。

- `literature/references.json`：原始书目记录。
- `literature/doi-verification-2026-10-07/`：DOI 核验、直接支持清单、原检索候选与来源说明；核对集仅在检索结束后用于评估。
- `SOURCE_MANIFEST.json`：上述文献材料的源路径和 SHA-256；离线测试验证内容未变。
- `retrieval/case.json`：两条分支的研究需求、种子、固定检索式和参数。
- `retrieval/baseline/`：固定回归基线，不是新运行输出。
- `retrieval/runs.json`：基线与历史复现实验的摘要。
- `test_timeline_study.py`：管线配置、基线比较和过程记录的离线测试。

真实检索入口为 `python -m scripts.timeline_retrieval`，波动实验入口为
`python -m scripts.timeline_variance`。运行缓存、日志和输出均写入
`artifacts/runs/<new-run>/`，详见 [检索管线说明](retrieval/README.md)。

原包中的聊天记录、时间线重构、图表、功能转换脚本及报告已移至
`artifacts/archive/timeline-study/`，不再作为检索测试依赖。保留的文献输入逐字节不变，
manifest 仅调整保留范围和相对位置。此案例不包含论文 PDF 或全文；书目及元数据核验不等于全文证据核验。
