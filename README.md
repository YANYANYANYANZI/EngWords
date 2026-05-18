# EngWords

EngWords 是一个面向英语词汇学习的本地项目，包含两部分核心内容：

1. **语义聚类 / 分词脚本**：将原始词表按语义聚成大单元，并进一步细分为子单元。
2. **VocabOS 词汇学习系统**：基于聚类后的词库，提供本地词卡学习、打卡、笔记、例句、搜索、仪表盘和黑暗模式。

---

## 目录结构

```text
EngWords/
├── README.md                 # 根目录总览
├── .gitignore
├── vocab_cluster.py           # 将原始词表聚成 12 个大单元
├── vocab_subcluster.py        # 将大单元继续细分为子单元
├── clustered_words.xlsx       # 大单元聚类结果
├── subclustered_words.xlsx    # 子单元聚类结果
└── vocab_os/                  # 本地词汇学习系统
    ├── README.md              # VocabOS 详细说明 / 维护指南
    ├── init_data.py           # 从 Excel 初始化 JSON 词库
    ├── subclustered_words.xlsx
    ├── backend/               # FastAPI 后端
    ├── frontend/              # 原生 HTML/CSS/JS 前端
    └── data/                  # JSON 词库、单元概述、关系数据
```

---

## 词库生成流程

### 1. 大单元聚类

`vocab_cluster.py` 使用 `sentence-transformers` 将词表转为语义向量，再用 K-Means 聚成 12 个大单元。

```bash
python vocab_cluster.py
```

默认输出：

```text
clustered_words.xlsx
```

> 注意：脚本当前示例输入路径为本机绝对路径 `/Users/leron/Desktop/考研词汇表.xlsx`，如换机器运行，需要修改 `vocab_cluster.py` 中的 `input_excel`。

### 2. 子单元细分

`vocab_subcluster.py` 读取 `clustered_words.xlsx`，将每个大单元继续按语义拆分为约 90 词一个子单元。

```bash
python vocab_subcluster.py
```

默认输出：

```text
subclustered_words.xlsx
```

---

## VocabOS 本地学习系统

VocabOS 是无前端构建步骤、无前端框架、以 JSON 文件作为数据库的轻量词汇学习系统。

主要功能：

- 单元 / 子单元词卡学习
- 今日打卡、过去掌握、复习次数统计
- 默认例句、自定义例句
- 独立笔记：新增、编辑、删除、转例句、关联其他单词
- 自定义例句：发音、转笔记、删除
- 中英文搜索、语义相关词 / 反义词搜索
- 单元概述编辑
- 学习仪表盘
- 黑暗模式

详细运行方式见：

```text
vocab_os/README.md
```

快速启动示例：

```bash
cd vocab_os
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

另开一个终端：

```bash
cd vocab_os
python -m http.server 8080 --directory frontend
```

访问：

```text
http://127.0.0.1:8080/index.html
```

---

## 主要依赖

词库聚类脚本：

```bash
pip install pandas openpyxl sentence-transformers scikit-learn
```

VocabOS 后端：

```bash
pip install fastapi uvicorn pandas openpyxl
```

可选：

```bash
pip install nltk
```

---

## GitHub

当前仓库：

```text
https://github.com/YANYANYANYANZI/EngWords
```

---

## 维护说明

- 根目录保留词库生成脚本和 Excel 中间结果，便于重新生成词库。
- `vocab_os/data/` 是 VocabOS 当前使用的 JSON 数据库，修改词卡、笔记、例句、打卡状态会落盘到这里。
- `.gitignore` 已排除系统文件、IDE 配置、Python 缓存、运行日志 pid、环境变量和依赖目录。
- 修改 `vocab_os/frontend/app.js` 或 `app.css` 后，建议同步更新 `vocab_os/frontend/index.html` 中的静态资源版本号，避免浏览器缓存旧文件。
