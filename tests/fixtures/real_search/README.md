# 古典园林真实检索回归集 v1

唯一维护入口是项目根目录的 `python -m scripts.real_search`。原本地 `SCI/system_test` 输入已迁到这里；不需要下载或提交 PDF 即可运行。

| 文件 | 用途 |
|---|---|
| `core_literature.txt` | 三篇种子 DOI，每行一篇 |
| `research_intent.txt` | 原始中文研究意图 |
| `case.json` | 全部运行参数、固定的三条基础查询、四个分支、模型与召回门槛 |
| `gold.json` | 十篇核对文献的 DOI、完整题名、角色和本地 PDF 映射 |
| `baselines.json` | 两轮已完成真实运行在同一核对集上的机器重算摘要 |

```bash
.venv/bin/python -m scripts.real_search plan
.venv/bin/python -m scripts.real_search run --out corpora/garden-v1-dev001
.venv/bin/python -m scripts.real_search evaluate corpora/garden-v1-dev001/corpus.json --out corpora/garden-v1-audit001
```

`plan` 和 `evaluate` 完全离线。`run` 使用真实 DeepSeek/WoS/OpenAlex，输出目录必须不存在，每次隔离 HTTP 缓存；需要 `.env` 或环境变量中的 API 配置。默认产物仅写到指定输出目录的 Obsidian 子目录，不使用个人笔记库路径。

分支：`vegetation_tls`、`garden_syntax`、`garden_reviews`、`heritage_pointcloud`。基础查询来自第二次真实运行，现固定以减少后续对比的混杂；意图解析及相关度评分仍由实时模型完成。核对集只在检索结束后读取匹配，不把目标 DOI 注入搜索。

非种子命中以 DOI 精确归一化匹配，每个目标至多计一次；分母固定为 7。三个种子另列，核心/方法/综述角色分别统计；分数是系统模型评分，不是独立人工评价。低于 6/7、种子不全/额外注入、年份未知/越界、重复 ID/DOI、引用关系无效或真实运行查询与固定配置不同，退出码均非零，且保留报告。

十篇子集是最初运行后复盘整理的开发回归集，不能声称预注册盲测、全包召回率或全库精确率。修改此集合或检索参数应增加用例版本，保留旧结果；API 索引与模型漂移也会导致变动。
