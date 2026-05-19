# EngWords

EngWords 是一个本地英语词汇学习项目，当前核心可分为两部分：

1. 根目录词库整理脚本：把原始词表按语义聚成 `Unit / SubUnit`。
2. `vocab_os/`：实际使用中的本地词卡系统，包含 FastAPI 后端、原生前端、SQLite 数据库、Tatoeba 例句和 GPT-SoVITS TTS 接口。

当前以 `vocab_os/` 为主，根目录聚类脚本是离线数据准备工具，不是日常运行入口。

## 仓库结构

```text
EngWords/
├── README.md
├── vocab_cluster.py
├── vocab_subcluster.py
└── vocab_os/
    ├── README.md
    ├── requirements.txt
    ├── backend/
    ├── data_pipeline/
    ├── frontend/
    ├── scripts/
    ├── data/
    ├── db/
    └── media/
```

## 当前状态

- 主应用已切到 SQLite + Async SQLAlchemy。
- 兼容路由 `/api/units`、`/api/words/{unit_id}`、`/api/update_word` 等已经代理到数据库实现。
- 数据库当前规模：
  - `words`: 6946
  - `clusters`: 84
  - `examples.source_type='tatoeba'`: 7916
  - `examples.source_type='user'`: 37
- Tatoeba 英中例句缓存位于 `vocab_os/data/tatoeba/`。
- GPT-SoVITS 的 `fast-langdetect` 大模型已确认应放在：
  `GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin`

## 快速启动

日常使用只需要启动 `vocab_os/`。

后端：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

前端：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python -m http.server 8080 --directory frontend
```

访问：

```text
http://127.0.0.1:8080/index.html
```

完整启动、初始化、Tatoeba 导入、TTS 依赖和已知问题见：

```text
vocab_os/README.md
```

## 词库聚类脚本

如果要重新生成 Excel 词库：

```bash
python vocab_cluster.py
python vocab_subcluster.py
```

注意：

- 这两个脚本不是 VocabOS 运行所必需。
- 脚本里可能仍包含本机路径假设，换机器运行前要先检查输入文件路径。

## 已知问题

- 当前仓库正在从旧 JSON 词库迁移到 SQLite；旧 README 中“JSON 仍是主存储”的说法已经过时。
- TTS 不内置在本仓库里，依赖外部 GPT-SoVITS 服务。
- `base311` 环境里的 PyTorch 已重装为 arm64 稳定版，但 `torch.backends.mps.is_available()` 仍为 `False`；这意味着 macOS MPS 加速问题尚未解决。
- 工作区当前存在较多未提交的数据与前端改动，提交前应确认是否都需要进入同一个 commit。
