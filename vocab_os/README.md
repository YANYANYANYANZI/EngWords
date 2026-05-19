# VocabOS

VocabOS 是 EngWords 当前实际运行的本地英语词汇学习系统。它使用：

- FastAPI 后端
- 原生 HTML/CSS/JavaScript 前端
- SQLite + Async SQLAlchemy 数据层
- Tatoeba 英中例句
- 外部 GPT-SoVITS TTS 服务

这份 README 只描述当前真实状态，不保留已经过时的“JSON 仍是主链路”说明。

## 1. 项目路径

```text
/Users/leron/PycharmProjects/EngWords/vocab_os
```

## 2. 目录结构

```text
vocab_os/
├── README.md
├── requirements.txt
├── backend/
│   ├── app.py
│   ├── models.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   └── init_db.py
│   └── orm/
├── data_pipeline/
│   ├── import_legacy_json.py
│   └── import_ecdict.py
├── scripts/
│   └── import_tatoeba.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── app.css
├── data/
│   ├── relations.json
│   ├── unit_summaries/
│   └── tatoeba/
├── db/
│   └── vocabos.sqlite3
└── media/
    └── audio/
```

## 3. 当前数据状态

当前数据库统计：

- 单词数：6946
- 聚类数：84
- Tatoeba 例句：7916
- 用户例句：37

例句缓存目录：

```text
data/tatoeba/
├── eng-cmn_links.tsv.bz2
├── eng_sentences.tsv.bz2
└── cmn_sentences.tsv.bz2
```

当前默认例句行为：

- 词卡顶部的 `default_example` 优先读取数据库里的系统例句。
- 当前优先级是：`tatoeba` > 其他系统来源 > 模板兜底句。
- “自定义例句”区域只显示真正用户例句，不再显示历史 `legacy_json` 批量模板句。

## 4. 运行环境

当前默认环境是：

```text
/Users/leron/miniconda3/envs/base311
```

安装依赖：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/pip install -r requirements.txt
```

`requirements.txt` 当前包含：

- `fastapi`
- `uvicorn`
- `pandas`
- `openpyxl`
- `sqlalchemy>=2.0`
- `aiosqlite`
- `greenlet`
- `pydantic`
- `python-dotenv`
- `httpx`

可选依赖：

```bash
/Users/leron/miniconda3/envs/base311/bin/pip install nltk
```

如果安装了 NLTK，`/api/dict/{word}` 会尝试使用 WordNet 提供补充释义、例句、近义词和反义词。

## 5. 启动说明

### 5.1 启动后端

必须从 `vocab_os` 根目录启动：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

不要用下面这种方式：

```bash
cd backend
uvicorn app:app
```

原因是 `backend/app.py` 依赖包内相对导入和项目根目录上下文。

### 5.2 启动前端

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python -m http.server 8080 --directory frontend
```

### 5.3 访问地址

- 前端：`http://127.0.0.1:8080/index.html`
- API：`http://127.0.0.1:8000/api/units`
- 数据库健康检查：`http://127.0.0.1:8000/api/db_health`

### 5.4 常用后台启动方式

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
mkdir -p .runlogs
nohup /Users/leron/miniconda3/envs/base311/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 > .runlogs/backend.log 2>&1 &
nohup /Users/leron/miniconda3/envs/base311/bin/python -m http.server 8080 --directory frontend > .runlogs/frontend.log 2>&1 &
```

查看日志：

```bash
tail -f .runlogs/backend.log
tail -f .runlogs/frontend.log
```

## 6. 数据初始化与导入

### 6.1 建表

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python -m backend.core.init_db
```

### 6.2 导入旧词库

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python -m data_pipeline.import_legacy_json
```

这个步骤会把旧词库导入 SQLite。当前兼容 API 已经主要读数据库，不应再把旧 JSON 当成主数据源理解。

### 6.3 导入 ECDICT

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python -m data_pipeline.import_ecdict /path/to/ecdict.csv
```

设计目标是只补全已经存在于学习词库中的词，不做全量词典导入。

### 6.4 导入 Tatoeba 英中例句

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python scripts/import_tatoeba.py
```

如果需要重建 Tatoeba 例句：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
/Users/leron/miniconda3/envs/base311/bin/python scripts/import_tatoeba.py --replace
```

当前脚本行为：

- 自动下载并缓存 Tatoeba 官方导出到 `data/tatoeba/`
- 筛选英文长度 `20 ~ 100`
- 使用 `\bword\b` 精确正则边界匹配
- 每个词最多挑选 2 条例句
- 写入 `examples` 表，`source_type='tatoeba'`
- 幂等插入，已存在的 `(word_id, text, source_type)` 会跳过

## 7. API 概览

### 7.1 当前主要路由

兼容路由：

```text
GET  /api/units
GET  /api/words/{unit_id}
GET  /api/all_words
POST /api/update_word
POST /api/update_note
POST /api/enrich_word
GET  /api/dashboard
GET  /api/dict/{word}
GET  /api/search/{query}
GET  /api/relations
GET  /api/unit_summary/{unit_id}
POST /api/unit_summary
```

数据库显式路由：

```text
GET  /api/db/units
GET  /api/db/words/{unit_id}
GET  /api/db/all_words
GET  /api/db/dashboard
POST /api/db/update_word
POST /api/db/update_note
POST /api/db/enrich_word
GET  /api/db/tts
GET  /api/db_health
```

说明：

- 兼容路由和 `/api/db/*` 现在都落到数据库后端。
- 前端默认仍使用兼容路由，所以旧 URL 不需要改。

## 8. 前端行为说明

前端是无构建链路的原生静态页面。

当前主要功能：

- Unit / SubUnit 列表
- 词卡展示
- 今日打卡 / 过去掌握
- 独立笔记
- 自定义例句
- 默认例句朗读
- 搜索
- 仪表盘
- 黑暗模式

缓存注意：

- 修改 `frontend/app.js` 或 `frontend/app.css` 后，记得同步更新 `frontend/index.html` 中的版本号。
- 否则浏览器可能继续加载旧静态资源。

## 9. TTS 说明

### 9.1 当前实现

后端 TTS 接口是：

```text
GET /api/db/tts?word=example&voice=nahida
```

它不是本地直接推理，而是转发到外部 GPT-SoVITS HTTP 服务：

```text
VOCABOS_TTS_API_URL
默认值: http://127.0.0.1:9880/tts
```

### 9.2 当前固定参考音频

`backend/app.py` 当前写死了：

- 参考音频：`media/audio/nahida/nahida_ref.wav`
- `prompt_text`
- `prompt_lang=zh`
- `text_lang=en`

这意味着当前 TTS 主要是为纳西妲音色的英语单词发音配置的。

### 9.3 GPT-SoVITS 相关外部依赖

当前外部项目路径：

```text
/Users/leron/PycharmProjects/_external/GPT-SoVITS
```

`fast-langdetect` 大模型需要放在：

```text
/Users/leron/PycharmProjects/_external/GPT-SoVITS/GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin
```

这个位置是 GPT-SoVITS 代码自己在 `LangSegmenter` 中指定的，不是系统默认缓存目录。

## 10. 验证命令

后端语法检查：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
python -m py_compile backend/app.py backend/models.py
```

前端语法检查：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
node --check frontend/app.js
```

接口检查：

```bash
curl -sS http://127.0.0.1:8000/api/db_health
curl -sS http://127.0.0.1:8000/api/units | jq '.[0]'
curl -sS http://127.0.0.1:8000/api/words/Unit_2_Sub6 | jq '.[0] | {word, default_example, example_sentences}'
```

Tatoeba 数据检查：

```bash
sqlite3 db/vocabos.sqlite3 "select source_type, count(*) from examples group by source_type;"
```

## 11. 当前已知问题

1. TTS 依赖外部 GPT-SoVITS 服务，不是本仓库自包含能力；只启动 VocabOS 不等于 TTS 可用。
2. 当前 `base311` 环境虽然已经安装 arm64 稳定版 PyTorch，但 `torch.backends.mps.is_available()` 仍为 `False`。这说明 macOS MPS 链路仍有问题，GPT-SoVITS 相关性能和设备选择不能假定正常。
3. `backend/app.py` 中仍包含部分写死的本机绝对路径和固定 TTS 参数，跨机器移植性一般。
4. `frontend/app.js` 仍是单文件原生脚本，功能继续增加后维护成本会持续上升。
5. 仓库当前有正在进行中的迁移与数据改动，某些旧 README、旧脚本说明、旧 JSON 假设已经不可靠；排障时应以数据库和当前路由实现为准。
6. `relations.json` 体积较大，阅读和调试时不要整体打印。
7. `backend/core/`、`media/` 目录里存在 `.DS_Store` 和 `__pycache__` 类文件痕迹，提交前应继续注意清理无关噪音。

## 12. 维护建议

- 后续功能优先围绕数据库模型和服务链路做，不要再把复杂能力堆回旧 JSON 架构。
- 处理例句时要区分三类数据：
  - 系统默认例句：如 `tatoeba`
  - 用户例句：`source_type='user'`
  - 历史遗留模板句：不要再当作用户内容展示
- 如果继续增强 TTS，先把配置从 `backend/app.py` 的硬编码中拆出来。
- 如果继续扩展前端，至少先把 `app.js` 按 API、状态、渲染拆分模块，再考虑是否引入框架。
