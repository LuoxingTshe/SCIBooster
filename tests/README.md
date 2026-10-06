# 测试目录

- 根目录下的 `test_*.py`：离线单元与集成测试，使用 `conftest.py` 中的模拟 API 客户端。
- `system/`：系统测试输入的可用性校验；真实 API 的人工验收和运行报告单独放在语料目录中。
- `fixtures/`：小型 JSON API 响应样本，供离线测试使用。
- `SCI/`：本地人工 PDF 包（Git 忽略）。`SCI` 与 `sci` 在本机是同一路径；测试不依赖此目录存在。
- `fixtures/real_search/`：可提交的固定真实测试用例、核对集和历史基线，适用于 Linux 和 macOS。
- `../corpora/`：真实 API 运行的语料、日志、报告及 Obsidian 导出（包括 `real-test-classical-garden-*` 和 `garden-v1-*`），不属于自动离线测试夹具。

离线测试：

```bash
python -m pytest -q
```

真实 API 测试的命令与验收集见 [`fixtures/real_search/README.md`](fixtures/real_search/README.md)。
