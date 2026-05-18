# VocabOS

VocabOS 是一个本地运行的英语词汇学习系统，当前版本包含 Excel/JSON 词库数据、FastAPI 后端、原生 HTML/CSS/JS 前端 SPA、词卡学习、打卡、笔记、默认例句、自定义例句、搜索、仪表盘和黑暗模式。

> 给后续维护 AI 的重点：这是一个**无构建步骤、无前端框架、以 JSON 文件作为数据库**的轻量项目。修改功能时优先保持简单，不要引入复杂框架，除非用户明确要求。

---

## 1. 项目路径与目录结构

项目根目录：

```bash
/Users/leron/PycharmProjects/EngWords/vocab_os
```

核心文件：

```text
vocab_os/
├── README.md                     # 项目说明 / 维护指南
├── init_data.py                   # 从 Excel 初始化 JSON 数据
├── subclustered_words.xlsx        # 源词表
├── backend/
│   ├── __init__.py
│   ├── app.py                     # FastAPI API、搜索、默认例句、dashboard
│   ├── db.py                      # JSON 文件读写、状态/笔记/例句落盘
│   └── models.py                  # Pydantic 请求/响应模型
├── frontend/
│   ├── index.html                 # SPA 页面结构
│   ├── app.js                     # 前端交互、搜索、词卡、笔记菜单、黑暗模式
│   └── app.css                    # UI 样式、深色模式、卡片/仪表盘
└── data/
    ├── units.json                 # 单元索引
    ├── relations.json             # 预生成相关词关系，体积较大
    ├── Unit_*.json                # 每个子单元的词卡数据
    └── unit_summaries/*.md        # 每个子单元概述
```

---

## 2. 运行环境与依赖

当前主要使用 `base311` conda 环境运行。

基础依赖：

```bash
pip install pandas openpyxl fastapi uvicorn
```

可选依赖：

```bash
pip install nltk
```

说明：

- 后端 `/api/dict/{word}` 会尝试使用 `nltk.corpus.wordnet` 获取释义/例句/近反义词。
- 如果没有 NLTK 或 WordNet 数据，后端不会崩，会使用本地词库和内置默认例句兜底。
- 当前不要在请求时自动 `nltk.download()`，会导致接口卡住或联网失败。

---

## 3. 快速一键启动（推荐）

推荐使用下面命令启动后端 + 前端，并自动打开页面：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os && \
mkdir -p .runlogs && \
(lsof -tiTCP:8000 -sTCP:LISTEN | xargs -r kill) && \
(lsof -tiTCP:8080 -sTCP:LISTEN | xargs -r kill) && \
sleep 1 && \
nohup conda run -n base311 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 > .runlogs/backend.log 2>&1 & echo $! > .runlogs/backend.pid && \
nohup conda run -n base311 python -m http.server 8080 --directory frontend > .runlogs/frontend.log 2>&1 & echo $! > .runlogs/frontend.pid && \
sleep 2 && \
open 'http://127.0.0.1:8080/index.html?force=4'
```

访问地址：

- 前端：`http://127.0.0.1:8080/index.html?force=4`
- 后端 API：`http://127.0.0.1:8000/api/units`

查看日志：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os

tail -f .runlogs/backend.log
# 或
tail -f .runlogs/frontend.log
```

停止服务：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
kill $(cat .runlogs/backend.pid) $(cat .runlogs/frontend.pid)
```

常见启动坑：

- `Address already in use`：8000 或 8080 被占用，用上面一键启动命令会自动 kill 旧进程。
- 后端不能用 `cd backend && uvicorn app:app` 启动，因为 `app.py` 使用相对导入 `from . import db`。
- 正确后端启动方式必须从 `vocab_os` 目录启动：

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

---

## 4. 数据模型

每个单词存在 `data/Unit_x_Suby.json` 中，基本结构：

```json
{
  "word": "background",
  "translation": "n.背景;出身",
  "unit": "Unit_2_Sub6",
  "status": {
    "memorized_past": false,
    "memorized_today": false,
    "last_reviewed": null,
    "review_count": 0
  },
  "notes": "",
  "pos": null,
  "definitions": [],
  "example_sentences": [],
  "chinese": null
}
```

运行时后端还会额外返回：

```json
{
  "default_example": "A measurable background often requires consistent effort..."
}
```

重要概念：

- `translation`：词库原始中文释义。
- `notes`：旧版兼容字段，由 `notes_v2[].text` 自动拼接生成，仍可被搜索/旧逻辑读取。
- `notes_v2`：新版独立笔记数组。每条笔记拥有 `id`、`text`、`links`、`created_at`、`updated_at`，可独立编辑、删除、转换例句、关联到其他单词。
- `example_sentences`：用户自定义例句，通常由笔记转成，可以删除/转回笔记/发音。
- `default_example`：系统默认例句，后端动态生成或未来从题库映射；**不写入 JSON，前端不可删除**。
- `definitions` / `pos` / `chinese`：可通过 `/api/enrich_word` 写入，但当前前端已经移除了“补全释义/例句”按钮。

---

## 5. 当前 API

### 单元与词卡

```http
GET /api/units
GET /api/words/{unit_id}
GET /api/all_words
```

`GET /api/words/{unit_id}` 返回该单元所有词卡，并附带动态字段 `default_example`。

### 状态与笔记

```http
POST /api/update_word
```

请求：

```json
{
  "unit": "Unit_2_Sub6",
  "word": "background",
  "memorized_past": true,
  "memorized_today": true
}
```

```http
POST /api/update_note
```

请求：

```json
{
  "unit": "Unit_2_Sub6",
  "word": "background",
  "notes": "用户笔记"
}
```

### 例句/释义落盘

```http
POST /api/enrich_word
```

请求：

```json
{
  "unit": "Unit_2_Sub6",
  "word": "background",
  "pos": "n",
  "definitions": ["n: the situation or context"],
  "example_sentences": ["自定义例句"],
  "chinese": "背景"
}
```

目前前端用它来保存/删除自定义例句。

### 字典与搜索

```http
GET /api/dict/{word}
GET /api/search/{query}?limit=12
GET /api/relations
```

搜索逻辑在 `backend/app.py`：

- `get_word_corpus()`：缓存加载全部词库。
- `_search_score()`：基于英文、中文释义、定义字段、模糊相似度打分。
- 写入笔记/状态/例句后会调用 `get_word_corpus.cache_clear()`，避免搜索缓存陈旧。

### 仪表盘

```http
GET /api/dashboard
```

返回总词量、今日复习、已掌握、复习率等数据。

### 单元概述

```http
GET /api/unit_summary/{unit_id}
POST /api/unit_summary
```

概述文件存储于：

```text
data/unit_summaries/Unit_x_Suby.md
```

---

## 6. 前端功能说明

前端没有构建工具，直接由 `python -m http.server` 服务静态文件。

主要文件：

- `frontend/index.html`：页面结构、按钮、容器。
- `frontend/app.js`：全部业务交互逻辑。
- `frontend/app.css`：全部样式和黑暗模式。

当前前端功能：

- 左侧单元/子单元列表。
- 普通搜索：输入时本地搜索 `allWords`。
- 语义/模糊搜索：调用 `/api/search/{query}`。
- 点击搜索结果：跳转到目标单元、滚动到目标单词卡片、高亮，并显示“返回上一级”。
- 单词发音：使用浏览器 `SpeechSynthesisUtterance`。
- 默认例句：每张卡片固定显示，只能发音。
- 自定义例句：来自 `example_sentences`，每条后面有 `⋯` 菜单：发音、转换成独立笔记、删除例句。
- 笔记区域：使用 `notes_v2` 多条独立笔记；每条笔记独立失焦保存，支持转换为例句、关联到其他单词、删除。关联时可选择：
  - 默认同步关联：目标词生成一条带来源的关联笔记，后续编辑源笔记时会同步更新目标关联笔记。
  - 作为副本：目标词生成独立副本，后续不跟随源笔记更新。
- 仪表盘：Chart.js + 统计卡片。
- 黑暗模式：`themeToggle` 按钮切换，状态存 `localStorage.vocab_theme`；样式统一使用 CSS 变量覆盖卡片、文字、表单、菜单、例句块、标签与打卡状态。

---

## 7. 浏览器缓存注意事项

前端静态文件容易被浏览器缓存。每次改 `app.js` 或 `app.css` 后，请同步更新 `index.html` 中的版本号：

```html
<link rel="stylesheet" href="app.css?v=20260518-4" />
<script src="app.js?v=20260518-4"></script>
```

如果用户反馈“UI 没变 / 搜索没反应”，优先检查：

1. `curl http://127.0.0.1:8080/index.html?force=xxx` 是否返回最新版本号。
2. 浏览器是否需要 `Cmd + Shift + R` 强刷。
3. `node --check frontend/app.js` 是否有 JS 语法错误。
4. 后端是否真的运行在 8000。

---

## 8. 如何添加/修改功能

### 8.1 新增后端 API

1. 在 `backend/models.py` 添加请求/响应模型。
2. 在 `backend/app.py` 添加路由。
3. 如果涉及 JSON 文件读写，优先在 `backend/db.py` 添加函数。
4. 如果写入了单词相关数据，记得清理缓存：

```python
get_word_corpus.cache_clear()
```

5. 验证：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
python -m py_compile backend/app.py backend/db.py backend/models.py
```

### 8.2 修改词卡字段

1. 修改 `backend/models.py` 的 `WordEntry`。
2. 修改 `data/Unit_*.json` 的实际数据结构（如果是持久字段）。
3. 修改 `backend/db.py` 的读写逻辑。
4. 修改 `frontend/app.js` 的 `renderWordGrid()`。

注意：

- `default_example` 是动态字段，不落盘。
- `example_sentences` 是自定义例句，落盘。

### 8.3 增加真实四六级/雅思例句库

推荐新增文件：

```text
data/example_bank.json
```

建议结构：

```json
{
  "achievement": [
    {
      "sentence": "...",
      "source": "IELTS Writing Task 2",
      "translation": "..."
    }
  ]
}
```

实现建议：

1. 在 `backend/db.py` 新增 `load_example_bank()`。
2. 在 `backend/app.py` 的 `_default_example()` 中优先查题库。
3. 优先级：题库例句 > WordNet 例句 > 内置兜底例句。
4. 前端默认例句块可以展示 `source`，但默认例句仍不可删除。

### 8.4 修改搜索逻辑

后端搜索在 `backend/app.py`：

- `_search_score(query, item)`：调整得分策略。
- `semantic_search()`：返回 related / opposite。
- `get_word_corpus()`：缓存全部词库。

前端搜索在 `frontend/app.js`：

- `localSearch()`：普通搜索。
- `performSemanticSearch()`：语义搜索按钮/回车。
- `renderSearchResults()` / `renderSemanticResults()`：结果渲染与跳转。

如果要做真正语义向量搜索，建议不要每次请求加载模型。应离线生成 embedding 缓存，例如：

```text
data/search_index.json
```

### 8.5 修改 UI

主要改：

- `frontend/index.html`：新增按钮/容器。
- `frontend/app.css`：样式、响应式、黑暗模式。
- `frontend/app.js`：交互事件和渲染逻辑。

修改 UI 后记得更新静态资源版本号。

---

## 9. 当前已知限制

1. 没有真正的四六级/雅思真题例句库，目前默认例句是后端动态兜底生成。
2. 搜索是本地启发式模糊搜索，不是真正 embedding 语义搜索。
3. 数据直接写 JSON 文件，适合本地单人使用，不适合多人并发。
4. 前端是原生 JS，随着功能增加，`app.js` 会越来越大；如果继续扩展，可以考虑拆分模块，但暂时不要贸然引入 React/Vue。
5. `relations.json` 很大，读取时注意不要整文件打印到上下文中。

---

## 10. 快速验证命令

检查后端语法：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
python -m py_compile backend/app.py backend/db.py backend/models.py
```

检查前端 JS 语法：

```bash
cd /Users/leron/PycharmProjects/EngWords/vocab_os
node --check frontend/app.js
```

验证 API：

```bash
curl -sS http://127.0.0.1:8000/api/units | jq '.[0]'

curl -sS http://127.0.0.1:8000/api/words/Unit_2_Sub6 | jq '.[0] | {word, translation, default_example, example_sentences}'

curl -sS 'http://127.0.0.1:8000/api/search/%E8%83%8C%E6%99%AF?limit=3' | jq '.related'
```

验证前端是否服务新版：

```bash
curl -sS 'http://127.0.0.1:8080/index.html?force=4' | grep -n 'app.css\|app.js\|themeToggle\|searchBackBtn'
```

---

## 11. 给后续 AI 的维护原则

- 优先读这几个文件：`backend/app.py`、`backend/db.py`、`backend/models.py`、`frontend/app.js`、`frontend/app.css`、`frontend/index.html`。
- 不要直接假设当前浏览器加载的是最新前端文件，先检查版本号和缓存。
- 不要在 API 请求中下载大模型或语料。
- 修改 JSON 数据结构时要考虑已有 84 个 `Unit_*.json` 文件兼容性。
- 修改搜索/例句功能时要区分：
  - 默认例句：系统/题库提供，不落盘到单词 JSON，不允许用户删除。
  - 自定义例句：用户笔记转化，保存在 `example_sentences`，允许删除/转笔记/发音。
  - 独立笔记：保存在 `notes_v2`，`notes` 只是兼容拼接文本；新增笔记功能优先操作 `notes_v2`。
- 每次完成后至少跑：

```bash
python -m py_compile backend/app.py backend/db.py backend/models.py
node --check frontend/app.js
```
