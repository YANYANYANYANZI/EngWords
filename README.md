# EngWords

EngWords 是当前唯一主仓库和唯一运行入口。它包含：

- FastAPI 后端
- 原生 HTML/CSS/JavaScript 前端
- SQLite + Async SQLAlchemy 数据层
- Tatoeba 英中例句导入
- 外部 GPT-SoVITS TTS 接口
- ECDICT 词典补全脚本

项目已经从 `vocab_os/` 子目录结构提级到仓库根目录。`vocab_os/` 不再是应用入口。

## 目录结构

```text
EngWords/
├── README.md
├── .env.example
├── requirements.txt
├── backend/
├── frontend/
├── data/
│   ├── source/
│   ├── tatoeba/
│   └── unit_summaries/
├── data_pipeline/
├── scripts/
│   ├── setup_external.sh
│   ├── import_tatoeba.py
│   ├── fill_ai_examples.py
│   ├── init_data.py
│   ├── vocab_cluster.py
│   └── vocab_subcluster.py
├── db/
└── media/
```

## 快速启动

安装依赖：

```bash
cd /Users/leron/PycharmProjects/EngWords
/Users/leron/miniconda3/envs/base311/bin/pip install -r requirements.txt
```

复制本地配置：

```bash
cd /Users/leron/PycharmProjects/EngWords
cp .env.example .env
```

启动后端：

```bash
cd /Users/leron/PycharmProjects/EngWords
/Users/leron/miniconda3/envs/base311/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

启动前端：

```bash
cd /Users/leron/PycharmProjects/EngWords
/Users/leron/miniconda3/envs/base311/bin/python -m http.server 8080 --directory frontend
```

如果 `8080` 已被占用，可切到别的端口，例如：

```bash
cd /Users/leron/PycharmProjects/EngWords
/Users/leron/miniconda3/envs/base311/bin/python -m http.server 8081 --directory frontend
```

访问：

- 前端：`http://127.0.0.1:8080/index.html`
- 沉浸式刷词页：`http://127.0.0.1:8080/focus.html`
- API：`http://127.0.0.1:8000/api/units`
- 数据库健康检查：`http://127.0.0.1:8000/api/db_health`

## 沉浸式刷词（FSRS）

当前已经提供一个独立的聚焦刷词入口 `frontend/focus.html`，对应后端接口：

- `GET /api/db/study/today`
- `POST /api/db/study/review`

默认策略：

- 今日新词上限 `20`
- 今日复习上限 `50`
- 使用 `fsrs` 调度器进行 `Again / Hard / Good / Easy` 四档评分
- 新卡或回炉卡若短时间内再次到期，会自动回到当前学习会话队列
- 首次只展示单词与发音，翻牌后展示音标、释义、Tatoeba / AI 例句
- 支持快捷键：空格翻牌，数字 `1 2 3 4` 直接评分

## 数据初始化

建表：

```bash
python -m backend.core.init_db
```

导入旧 JSON 词库到 SQLite：

```bash
python -m data_pipeline.import_legacy_json
```

导入 Tatoeba 英中例句：

```bash
python scripts/import_tatoeba.py
```

批量补全 DeepSeek AI 例句：

```bash
python scripts/fill_ai_examples.py --limit 50
```

导入 ECDICT：

```bash
python -m data_pipeline.import_ecdict /path/to/ecdict.csv
```

## 外部依赖

`ECDICT` 和 `GPT-SoVITS` 不 vendoring 到本仓库。它们保持外部依赖形态。

初始化外部目录：

```bash
cd /Users/leron/PycharmProjects/EngWords
bash scripts/setup_external.sh
```

默认会准备：

- `../_external/GPT-SoVITS`
- `../_external/ECDICT`

你需要额外完成：

1. 把 `ecdict.csv` 放到 `../_external/ECDICT/`，或自定义 `ECDICT_CSV_PATH`
2. 单独启动 GPT-SoVITS 服务
3. 如需覆盖 TTS 地址或参考音频路径，在 `.env` 中设置：
   `VOCABOS_TTS_API_URL`
   `VOCABOS_TTS_REF_AUDIO_PATH`

本地启动纳西妲 TTS 的一个可用示例：

```bash
cd /Users/leron/PycharmProjects/_external/GPT-SoVITS
env \
  MPLCONFIGDIR=/private/tmp/gptsovits-mpl \
  NUMBA_CACHE_DIR=/private/tmp/gptsovits-numba \
  XDG_CACHE_HOME=/private/tmp/gptsovits-cache \
  PYTORCH_ENABLE_MPS_FALLBACK=1 \
  KMP_DUPLICATE_LIB_OK=TRUE \
  python api_v2.py \
  --bind_addr 127.0.0.1 \
  --port 9880 \
  --tts_config GPT_SoVITS/configs/tts_infer_nahida.yaml
```

如果后端需要显式指定参考音频，可这样启动：

```bash
cd /Users/leron/PycharmProjects/EngWords
env VOCABOS_TTS_REF_AUDIO_PATH=/Users/leron/PycharmProjects/EngWords/media/audio/nahida/nahida_ref.wav \
  /Users/leron/miniconda3/envs/base311/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

## 离线词库脚本

这些脚本不是日常运行入口，统一放在 `scripts/`：

- `scripts/vocab_cluster.py`
- `scripts/vocab_subcluster.py`
- `scripts/init_data.py`

示例：

```bash
python scripts/vocab_cluster.py /path/to/raw_words.xlsx
python scripts/vocab_subcluster.py
python scripts/init_data.py
```

## 当前说明

- 例句默认优先级为：`pinned > tatoeba > ai > movie > subtitle > default > user`
- `POST /api/db/swap_example` 可把现有例句置顶为默认例句
- 根目录现在是唯一 README、唯一启动路径、唯一项目入口
