# 本地运行数据

此目录统一保存检索缓存、运行输出及历史研究附件；除本说明外均不提交 Git。

- `cache/http.sqlite`：普通 build / agent / eval 共用的检索缓存。
- `runs/<run>/`：每次检索的语料、日志、报告、导出和 Obsidian vault。
- `runs/<case-run>/http.sqlite` 或分支目录中的缓存：固定真实案例的独立缓存，通过后默认清空；需要复用时加 `--keep-cache`。
- `archive/`：从测试目录移出的非检索研究材料及旧辅助文件。

默认目录由 `SCIB_CACHE_DIR=artifacts/cache` 和 `SCIB_CORPORA_DIR=artifacts/runs` 控制。
手动指定 `--out` 时也应写入 `artifacts/runs/`；真实测试每次使用新目录。
`tests/cases/` 仅保存文献包、固定输入、核对集、必要的回归基线和测试脚本，不写入新运行结果。

检索成功且语料与导出全部保存后，默认删除先前已完成的受管理运行，仅保留最新一次完整结果。
同时清空本次及共享 HTTP 缓存并回收数据库空间。空数据库文件保留，清理明细写入 `cleanup.json`。
`build`、完成的 `agent` 会话及通过检查的真实测试均执行此策略；Agent 续跑输出到新目录。
失败、中断、未完成会话及未通过的测试保留旧结果、缓存和诊断产物。

重复实验时使用 `--keep-history --keep-cache`；也可在 `.env` 设置
`SCIB_KEEP_HISTORY=true`、`SCIB_KEEP_CACHE=true`。波动实验将所有重复作为一份结果，
并保存源语料快照以便离线重算。仅清理带 `.scibooster-run.json` 管理标记且已完成的目录，
未识别目录、符号链接、文献包、archive 和外部 Obsidian vault 不纳入自动清理。
现有历史结果已登记，从下一次成功检索开始参与保留策略；回归失败的旧运行保留诊断状态。

2026-10-08：旧 `.cache/`、`corpora/` 已迁入；当天假山检索的原始、中间及去重输出已删除。
