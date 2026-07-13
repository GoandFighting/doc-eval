# 文档转换评测体系报告

> **版本**: 0.1.0  
> **日期**: 2026-07-06  
> **项目**: doc-eval — 文档转 Markdown 转换质量评测模块

---

## 1. 概述

### 1.1 目标

对文档转换工具（PDF → Markdown）的输出质量进行自动化、可量化、多维度的评测，输出 0-100 的综合分数及各维度明细，为转换工具的选型、调优和迭代提供数据支撑。

### 1.2 评测对象

转换工具的输出为**纯 Markdown 文本**，不含 bounding box、坐标等空间信息。评测体系围绕这一输出形态设计。

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| 规则优先 | 优先使用 ParseBench 的规则化评测，避免 LLM 评测的不确定性和成本 |
| 多维度加权 | 不同维度独立评分，按权重聚合为综合分数 |
| 可配置 | 各维度可独立开关，权重可自定义，缺失维度自动重归一化 |
| 可解释 | 每个维度输出子指标明细，支持溯源到具体规则 |

---

## 2. 评测维度总览

当前评测体系包含 5 个维度，其中 3 个来自 ParseBench，2 个为自实现层：

| 维度 | 来源 | 评测内容 | 默认权重 | 默认启用 |
|------|------|---------|---------|---------|
| content_faithfulness | ParseBench | 文本内容忠实度 | 0.30 | 是 |
| semantic_formatting | ParseBench | 语义格式保真度 | 0.25 | 是 |
| tables | ParseBench | 表格还原准确度 | 0.25 | 是 |
| format_quality | 自实现 (L1) | Markdown 格式规范度 | 0.10 | 是 |
| semantic | 自实现 (L4) | 语义相似度 | 0.10 | 否 |

> **权重重归一化**: 当某维度缺失（如 L4 未启用、或该 PDF 无对应测试用例）时，其权重按比例分配到其余维度，保证综合分数始终在 0-100 区间内有意义。

### 2.1 未纳入的维度

| 维度 | 原因 |
|------|------|
| Layout / Visual Grounding | 需要 bounding box 坐标信息，纯 Markdown 输出无法参与空间定位、分类匹配、归因检查和阅读顺序评测 |
| Charts | 数据集中无图表类测试用例 |

---

## 3. 各维度详解

### 3.1 Content Faithfulness（文本内容忠实度）

**来源**: ParseBench `text_content` 规则集  
**权重**: 0.30（最高权重）

#### 评测目标

检查转换后的 Markdown 是否忠实保留了原文档的文本内容，包括：
- 文本正确性：关键内容是否完整、无遗漏、无多余
- 顺序保持：段落/元素的排列顺序是否与原文一致
- 规则通过率：逐条规则检查的通过比例

#### 子指标

| 指标 | 说明 | 范围 |
|------|------|------|
| `normalized_text_correctness` | 归一化文本正确率 | 0-1 |
| `normalized_order` | 归一化顺序保持率 | 0-1 |
| `rule_pass_rate` | 规则通过率 | 0-1 |

#### 评分方式

综合分数 = `content_faithfulness` 复合指标 × 100（ParseBench 内部加权计算）

#### 数据规模

`text_content.jsonl` 包含 44,872 条测试用例，覆盖所有文本类 PDF。例如 `text_dense__de.pdf` 有 213 条内容规则。

---

### 3.2 Semantic Formatting（语义格式保真度）

**来源**: ParseBench `text_formatting` 规则集  
**权重**: 0.25

#### 评测目标

检查转换后的 Markdown 是否正确保留了原文档的语义格式标记，包括：
- 文本样式：加粗 `**bold**`、斜体 `*italic*` 等是否保留
- 标题准确性：标题层级和文本是否正确
- LaTeX 公式：数学公式是否正确转换为 LaTeX
- 代码块：代码块是否正确标识

#### 子指标

| 指标 | 说明 | 范围 |
|------|------|------|
| `normalized_text_styling` | 文本样式保真率 | 0-1 |
| `normalized_title_accuracy` | 标题准确率 | 0-1 |
| `normalized_latex` | LaTeX 公式保真率 | 0-1 |
| `normalized_code_block` | 代码块保真率 | 0-1 |
| `rule_pass_rate` | 规则通过率 | 0-1 |

#### 评分方式

综合分数 = `semantic_formatting` 复合指标 × 100

#### 数据规模

`text_formatting.jsonl` 包含 1,752 条测试用例。

---

### 3.3 Tables（表格还原准确度）

**来源**: ParseBench `table` 规则集  
**权重**: 0.25

#### 评测目标

检查转换后的表格（HTML 格式 Markdown）与标准答案的匹配程度。

#### 子指标

| 指标 | 说明 | 范围 |
|------|------|------|
| `grits_con` | GriTS 内容相似度（cell 级文本匹配） | 0-1 |
| `grits_trm_composite` | GriTS 综合分（结构 + 内容） | 0-1 |
| `table_record_match` | 表格记录匹配率 | 0-1 |
| `teds` | TEDS（Tree-Edit-Distance Similarity）| 0-1 |

#### 评分方式

优先使用 `grits_trm_composite`，若不可用则回退到 `grits_con`，乘以 100。

#### 数据规模

`table.jsonl` 包含 15 条测试用例。仅对表格类 PDF（如 `1 timetable (1)_page27.pdf`）产生该维度。

---

### 3.4 Format Quality（Markdown 格式规范度）

**来源**: 自实现 L1 层（`eval/layers/l1_format.py`）  
**权重**: 0.10  
**工具**: PyMarkdown lint (`pymarkdownlnt`)

#### 评测目标

检查转换后的 Markdown 是否符合 Markdown 格式规范，包括标题层级、空行、代码块围栏、列表格式等结构性规则。与 ParseBench 维度不同，L1 不关心内容是否正确，只关心 Markdown 语法是否规范。

#### 评分方式

1. 将转换后的 Markdown 写入临时文件
2. 运行 PyMarkdown lint，获取违规列表
3. 按规则 ID 查惩罚表累加扣分
4. 最终分数 = `max(0, 100 - min(总扣分, 100))`

#### 惩罚映射表

| 规则 ID | 说明 | 扣分 |
|---------|------|------|
| MD001 | 标题层级跳跃 | 3.0 |
| MD041 | 首行应为标题 | 2.0 |
| MD022 | 标题周围需空行 | 2.0 |
| MD023 | 标题须顶格 | 2.0 |
| MD024 | 重复标题 | 2.0 |
| MD025 | 仅一个 H1 | 2.0 |
| MD031 | 代码块周围需空行 | 1.5 |
| MD032 | 列表周围需空行 | 1.5 |
| MD029 | 有序列表前缀 | 1.5 |
| MD003 | 标题风格一致性 | 1.5 |
| MD010 | 硬 Tab | 1.0 |
| MD026 | 标题尾部标点 | 1.0 |
| MD040 | 代码块需语言标注 | 1.0 |
| MD009 | 尾部空格 | 0.5 |
| MD012 | 多余空行 | 0.5 |
| MD033 | 内联 HTML | 0.5 |
| 其他 | 未列出的规则 | 1.0 |

> 结构性规则（标题层级、空行）扣分较高，样式规则扣分较低。

---

### 3.5 Semantic（语义相似度）

**来源**: 自实现 L4 层（`eval/layers/l4_semantic.py`）  
**权重**: 0.10  
**默认状态**: 禁用（需安装 `sentence-transformers`）  
**模型**: `paraphrase-multilingual-MiniLM-L12-v2`

#### 评测目标

计算参考文本与转换后 Markdown 的语义相似度，捕捉字面不同但语义相同的情况。

#### 评分方式

1. 剥离 HTML 标签和 Markdown 标记，获取纯文本
2. 用 sentence-transformers 编码为向量
3. 计算余弦相似度
4. 分数 = 相似度 × 100

#### 适用范围

当前仅对表格类 PDF 有效（有 `expected_markdown` 可作为参考文本）。文本类 PDF 无单一参考 Markdown，L4 被跳过。

---

## 4. 评测流程

```
                    ┌─────────────────────────────────────────────┐
                    │              EvalRequest                      │
                    │  converted_md: str  (转换后的 Markdown)       │
                    │  pdf_name: str      (PDF 文件名)              │
                    └─────────────────┬───────────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────────────┐
                    │           AsyncEvalRunner.evaluate()         │
                    └─────────────────┬───────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                   ▼
            ┌──────────────┐  ┌──────────────┐   ┌──────────────┐
            │ ParseBench   │  │  L1 Format   │   │  L4 Semantic │
            │ Adapter      │  │  Evaluator   │   │  Evaluator   │
            │              │  │  (PyMarkdown) │   │  (可选)       │
            └──────┬───────┘  └──────┬───────┘   └──────┬───────┘
                   │                 │                   │
                   ▼                 │                   │
     ┌─────────────────────────┐     │                   │
     │  _extract_dimensions()  │     │                   │
     │  按 anchor 分割 metrics │     │                   │
     │  → content_faithfulness │     │                   │
     │  → semantic_formatting  │     │                   │
     │  → tables               │     │                   │
     └───────────┬─────────────┘     │                   │
                 │                   │                   │
                 ▼                   ▼                   ▼
     ┌───────────────────────────────────────────────────────┐
     │              List[DimensionScore]                      │
     └───────────────────────┬───────────────────────────────┘
                             │
                             ▼
     ┌───────────────────────────────────────────────────────┐
     │              _aggregate()                              │
     │  active_weights() 重归一化 → 加权求和                   │
     └───────────────────────┬───────────────────────────────┘
                             │
                             ▼
     ┌───────────────────────────────────────────────────────┐
     │                   EvalResponse                         │
     │  overall_score: float (0-100)                         │
     │  dimensions: List[DimensionScore]                     │
     │  metadata: {elapsed_seconds, version, metric_count}  │
     └───────────────────────────────────────────────────────┘
```

### 4.1 关键设计：Metric 分段

ParseBench 对同一个 PDF 可能运行多个测试用例（如 `text_content` + `text_formatting`），每个用例产生一组连续的 MetricValue 列表。两组指标中有重名项（如 `rule_pass_rate` 同时出现在两个段中）。

为避免混淆，runner 使用 **anchor 锚点** 进行分段：

- `content_faithfulness` 出现时 → 该段归为 content_faithfulness 维度
- `semantic_formatting` 出现时 → 该段归为 semantic_formatting 维度
- 表格指标（`grits_*`）不依赖锚点，从全局指标中提取

### 4.2 关键设计：权重重归一化

```python
# config.py — active_weights()
active = {k: v for k, v in self.weights.items() if k in available_dimensions and v > 0}
total = sum(active.values())
return {k: v / total for k, v in active.items()}
```

示例：L4 禁用 + PDF 无表格 → 可用维度 = {content_faithfulness, semantic_formatting, format_quality}

| 维度 | 原始权重 | 重归一化后 |
|------|---------|-----------|
| content_faithfulness | 0.30 | 0.462 |
| semantic_formatting | 0.25 | 0.385 |
| format_quality | 0.10 | 0.154 |

---

## 5. 数据集

### 5.1 数据集结构

```
newbench/
├── text_content.jsonl      # 44,872 行 — 文本内容忠实度规则
├── text_formatting.jsonl   #  1,752 行 — 语义格式保真度规则
├── table.jsonl             #     15 行 — 表格还原测试用例
├── layout.jsonl            #  2,638 行 — 版面检测规则（未使用）
├── selected_text/           # 文本类 PDF 文件
├── selected_table/          # 表格类 PDF 文件
└── selected_layout/         # 版面类 PDF 文件
```

### 5.2 测试用例格式

每行一个 JSON 对象，核心字段：

```json
{
  "pdf": "docs/text/text_dense__de.pdf",
  "category": "text_content",
  "id": "a1b2c3d4e5f6g7h8",
  "type": "parse",
  "rule": "{\"expected\": \"...\", \"mode\": \"contains\", ...}",
  "expected_markdown": null,
  "tags": ["easy"]
}
```

- `pdf` — PDF 文件路径（仅取文件名用于匹配）
- `rule` — JSON 编码的评测规则（包含期望值、匹配模式等）
- `expected_markdown` — 表格类用例有值，文本类为 null

### 5.3 PDF 覆盖

ParseBenchAdapter 加载所有 `ParseTestCase`（跳过 `LayoutDetectionTestCase`），按 PDF 文件名分组。不同 PDF 触发不同维度组合：

| PDF 类型 | 触发维度 |
|---------|---------|
| 文本类 (`text_*.pdf`) | content_faithfulness, semantic_formatting, format_quality |
| 表格类 (`*_page*.pdf`) | tables, format_quality, (semantic 如启用) |

---

## 6. 代码结构

```
eval/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── config.py          # EvalConfig — 权重、开关、数据集路径
│   ├── models.py          # EvalRequest, EvalResponse, DimensionScore
│   └── runner.py           # AsyncEvalRunner — 编排所有维度
├── adapters/
│   ├── __init__.py
│   └── parsebench.py      # ParseBenchAdapter — 桥接 ParseBench
├── layers/
│   ├── __init__.py
│   ├── l1_format.py       # L1FormatEvaluator — PyMarkdown lint
│   └── l4_semantic.py     # L4SemanticEvaluator — sentence-transformers
├── metrics/
│   ├── __init__.py
│   └── normalize.py       # to_100, clamp_100
└── report.py              # to_json, to_dict, print_summary

tests/
├── test_l1_format.py       # 4 tests — L1 格式评测
├── test_parsebench_adapter.py  # 6 tests — ParseBench 适配器
└── test_runner.py          # 4 tests — Runner 端到端

example_eval.py             # CLI 入口
pyproject.toml              # 项目配置
```

---

## 7. 使用方式

### 7.1 命令行

```bash
# 评测一个转换结果
python example_eval.py 转换结果.md text_dense__de.pdf

# 演示模式（用 expected_markdown 模拟满分）
python example_eval.py
```

### 7.2 编程调用

```python
import asyncio
from pathlib import Path
from eval.core.config import EvalConfig
from eval.core.models import EvalRequest
from eval.core.runner import AsyncEvalRunner
from eval.report import to_json

config = EvalConfig(
    dataset_dir=Path("newbench"),
    enable_l1=True,
    enable_l4=False,
)
runner = AsyncEvalRunner(config)

request = EvalRequest(converted_md=md_text, pdf_name="text_dense__de.pdf")
response = asyncio.run(runner.evaluate(request))

print(f"Overall: {response.overall_score}")
print(to_json(response))
```

### 7.3 输出示例

```json
{
  "overall_score": 72.35,
  "pdf_name": "text_dense__de.pdf",
  "dimensions": [
    {
      "dimension": "content_faithfulness",
      "score": 85.2,
      "metrics": {
        "normalized_text_correctness": 0.9123,
        "normalized_order": 0.8456,
        "rule_pass_rate": 0.7800
      },
      "metadata": {"source": "parsebench:text_content"}
    },
    {
      "dimension": "semantic_formatting",
      "score": 0.0,
      "metrics": {
        "normalized_text_styling": 0.0,
        "normalized_title_accuracy": 0.0,
        "normalized_latex": 0.0,
        "normalized_code_block": 0.0,
        "rule_pass_rate": 0.0
      },
      "metadata": {"source": "parsebench:text_formatting"}
    },
    {
      "dimension": "format_quality",
      "score": 88.5,
      "metrics": {},
      "metadata": {"evaluator": "pymarkdownlnt"}
    }
  ],
  "metadata": {
    "elapsed_seconds": 3.21,
    "version": "0.1.0",
    "metric_count": 12
  }
}
```

---

## 8. 测试覆盖

| 测试文件 | 测试数 | 覆盖内容 |
|---------|--------|---------|
| `test_l1_format.py` | 4 | 干净 Markdown 高分、空文本零分、违规 Markdown 低分、详细结果含违规列表 |
| `test_parsebench_adapter.py` | 6 | 测试用例加载、表格/文本 PDF 存在性、expected_md 评测、空 Markdown 评测、未知 PDF 报错 |
| `test_runner.py` | 4 | 可用 PDF 列表、表格文档端到端评测、空 Markdown 评测、响应可序列化 |
| **合计** | **14** | 全部通过 |

---

## 9. 依赖

| 依赖 | 用途 | 必需 |
|------|------|------|
| `parse-bench` | 规则化评测引擎 | 是 |
| `pymarkdownlnt` | Markdown lint (L1) | 是 |
| `sentence-transformers` | 语义相似度 (L4) | 否（可选） |
| `fastapi` + `uvicorn` | Web 服务 | 否（未来阶段） |
| `pytest` | 测试 | 开发环境 |

---

## 10. 局限性与改进方向

### 10.1 当前局限

| 局限 | 说明 |
|------|------|
| **无 Layout 维度** | 纯 Markdown 输出无 bbox，无法评测空间定位、元素分类、阅读顺序 |
| **L4 适用范围有限** | 仅表格类 PDF 有 `expected_markdown` 可作参考文本，文本类 PDF 的 L4 被跳过 |
| **表格测试用例少** | `table.jsonl` 仅 15 条，表格维度统计意义有限 |
| **L1 惩罚表为人工设定** | 各规则扣分权重基于经验，未经大规模校准 |
| **ParseBench 依赖** | 评测体系核心依赖 ParseBench，其版本变更可能影响指标输出 |
| **无批量评测** | 当前仅支持单文档评测，无批量跑全部 PDF 的能力 |

### 10.2 改进方向

| 方向 | 说明 |
|------|------|
| **批量评测** | 支持一次评测多个 PDF，输出汇总报告和排名 |
| **L4 扩展** | 为文本类 PDF 构建参考文本（如从 PDF 提取纯文本），使 L4 对所有 PDF 可用 |
| **权重校准** | 用标注数据或人工评测结果校准各维度权重 |
| **FastAPI 服务** | 提供 HTTP API，支持上传 Markdown + PDF 名获取评测结果 |
| **可视化报告** | 生成 HTML 报告，含维度雷达图、子指标柱状图、违规明细 |
| **历史趋势** | 记录每次评测结果，支持对比不同转换工具或同一工具不同版本 |
| **L1 惩罚表自动化** | 基于大规模数据统计各规则出现频率与人工评分的相关性，自动调整扣分权重 |
