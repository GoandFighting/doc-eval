# 文档转换评测平台

Document-to-Markdown 转换质量评测系统，基于 [ParseBench](https://github.com/run-llama/ParseBench) 规则评测 + 自定义 L1 格式质量 + 可选 L4 语义相似度，输出加权 0-100 综合评分。

## 功能

- **多维度评测**：内容准确性、格式保真度、表格、格式质量（L1 lint）、语义相似度（L4，可选）
- **Web 界面**：数据集下载、Markdown 上传、结果可视化（柱状图 + 动态表格）
- **多数据集支持**：内置 newbench 数据集 + 用户上传自定义数据集（JSONL 或 sidecar 格式）
- **批量评测**：异步并发，支持一次上传多个 MD 文件
- **CLI 入口**：`example_eval.py` 支持命令行单文件评测

## 快速开始

### 安装

```bash
git clone <repo-url>
cd doc-eval
pip install -e .
pip install ".[server]"  # 安装 Web 服务依赖
```

### 启动 Web 服务

```bash
python -m uvicorn server.app:app --reload --port 8000
```

浏览器打开 http://localhost:8000

### Docker 部署

```bash
docker build -t doc-eval .
docker run -p 8000:8000 doc-eval
```

### 命令行评测

```bash
# 评测单个 MD 文件
python example_eval.py 转换结果.md text_simple__10k.pdf

# 不带参数运行演示
python example_eval.py
```

## 使用流程

1. **下载数据集** — 在 Web 界面选择数据集，下载 PDF 文件包
2. **转换 PDF** — 用你的文档转换工具将 PDF 转为 Markdown
3. **上传 MD** — 将转换后的 `.md` 文件上传（文件名需与 PDF 对应，如 `foo.pdf` → `foo.md`）
4. **查看结果** — 系统自动评测并展示各维度得分

## 评测维度

| 维度 | 来源 | 权重 | 说明 |
|------|------|------|------|
| content_faithfulness | ParseBench text_content 规则 | 0.30 | 文本内容完整性、顺序正确性 |
| semantic_formatting | ParseBench text_formatting 规则 | 0.25 | 标题层级、加粗、代码块等格式保真度 |
| tables | ParseBench table (GriTS/TEDS) | 0.25 | 表格结构相似度 |
| format_quality | L1 (PyMarkdown lint) | 0.10 | Markdown 语法规范（MD001-MD041） |
| semantic | L4 (sentence-transformers) | 0.10 | 语义相似度（默认关闭，权重重分配） |

缺失维度的权重自动重新归一化。

## 项目结构

```
doc-eval/
├── eval/                    # 评测核心模块
│   ├── core/
│   │   ├── config.py        # 评测配置（权重、开关、并发数）
│   │   ├── models.py        # 数据模型（EvalRequest/Response/Batch）
│   │   ├── runner.py        # 异步评测运行器（四层流水线）
│   │   └── registry.py      # 多数据集注册管理
│   ├── adapters/
│   │   └── parsebench.py    # ParseBench 适配器（MD → InferenceResult 包装）
│   ├── layers/
│   │   ├── l1_format.py     # L1 格式质量（PyMarkdown lint）
│   │   └── l4_semantic.py   # L4 语义相似度（sentence-transformers）
│   ├── metrics/
│   │   └── normalize.py     # 分数归一化工具
│   └── report.py            # 报告生成（JSON/文本）
├── server/                  # FastAPI Web 服务
│   ├── app.py               # FastAPI 应用入口
│   ├── routes_dataset.py    # 数据集 API（list/upload/info/download）
│   ├── routes_eval.py       # 评测 API（batch）
│   ├── registry_holder.py   # 全局 registry 单例
│   └── static/
│       └── index.html       # 前端 UI（单文件 SPA）
├── tests/                   # 测试（30 个）
├── newbench/                # 内置数据集（JSONL 文件）
├── example_eval.py          # CLI 评测入口
└── pyproject.toml           # 项目配置
```

## 自定义数据集

支持两种格式上传（zip 压缩包）：

### JSONL 格式

```
my_dataset.zip
├── text_content.jsonl       # 文本内容规则
├── text_formatting.jsonl    # 文本格式规则
├── table.jsonl              # 表格评测（含 expected_markdown）
└── (可选) pdfs/             # PDF 文件
```

### Sidecar 格式

```
my_dataset.zip
├── group1/
│   ├── doc1.pdf
│   ├── doc1.test.json       # 测试规则 + 可选 expected_markdown
│   └── ...
└── ...
```

JSONL 每行格式参见 `newbench/text_content.jsonl` 示例。文件名不影响评测，维度由 `type` 字段和 `expected_markdown` 内容决定。

## 技术栈

- **Python 3.12+**
- **FastAPI** + **uvicorn** — Web 服务
- **ParseBench** — 规则评测引擎
- **PyMarkdown** — Markdown lint
- **sentence-transformers** — 语义相似度（可选）
- **pytest** — 测试

## 测试

```bash
python -m pytest tests/ -v
```

## License

MIT
