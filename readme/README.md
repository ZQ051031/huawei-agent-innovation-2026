# 环境、安装和部署 / Environment & deployment

- Python 3.10+、SQLite（Python 标准库）、支持现代 JavaScript 的浏览器。
- 在包根目录运行 `bash readme/install.sh`。开发或测试用 `bash readme/install.sh --dev`。安装时需能访问 Python 包索引（或将 pip 配置为本地 wheel 缓存）；安装后默认离线运行。
- `cd project && ../.venv/bin/python -m clearbooks serve`，打开 <http://127.0.0.1:8765/>；用 `--port` 换端口。仅绑定回环地址，不是多用户/公网服务，也不应配置公网反向代理。
- SQLite 默认存在 `~/.clearbooks/ledger.sqlite3`。使用 `CLEARBOOKS_DB` 或命令前的 `--db` 指定数据库。演示用独立数据库；停服务后备份数据库文件和任何使用中的 SQLite sidecar，或使用 SQLite 官方在线备份机制。SQLite 文件未加密，仅在受控设备使用。
- CLI、输入格式、预算、复核逻辑及可选模型见 [project README](../project/README.md)。

## 开源组件 / Open source

| Component | Purpose | Upstream license |
| --- | --- | --- |
| Python, including sqlite3 / SQLite | Runtime and storage | PSF / SQLite public domain |
| [pypdf](https://github.com/py-pdf/pypdf) | Text PDF extraction | BSD-3-Clause |
| [pytest](https://github.com/pytest-dev/pytest) | Test-only tooling | MIT |
| [python-pptx](https://github.com/scanny/python-pptx) | Deck generation only | MIT |
| [ReportLab](https://www.reportlab.com/) | Sample invoice generation only | BSD |
| [Chromium / Chrome](https://www.chromium.org/) | UI verification and print-to-PDF | Tool not distributed |
| [Noto Sans CJK](https://github.com/notofonts/noto-cjk) | Optional local Chinese display / PDF font embedding | SIL Open Font License 1.1 |

Code and fictional sample data are licensed under [MIT](../LICENSE). Official contest text is a separately attributed source extract, not project source code. For font attribution see [Noto Sans CJK license](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE).

## 码道应用总结（待参赛者实做核验）

官网要求开发过程以华为云码道为核心 AI 编程工具。本版本没有由本会话在码道中生成的使用证据，不应把下列计划当成已完成。建议参赛者实际使用码道迭代字段提取、重复规则和双语问答，用真实变更、失败前后测试及 commit 记录说明如何提升单人开发效率。证据清单与记录表见 [codearts_proof](../codearts_proof/README.md)。将真实结果补入路演稿与本节。
