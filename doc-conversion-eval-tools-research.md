## 文档转换评测工具调研报告

### 一、端到端评测框架（自带基准数据集）

**OmniDocBench** — 当前业界金标准。由 OpenDataLab 发布，CVPR 2025 收录。包含 1,355 页精标注 PDF，覆盖版面分析、表格识别、公式识别、阅读顺序等多维度评测。指标包括 BLEU、TEDS（表格编辑距离）、CDM（公式字符匹配）、mAP（版面检测）。MinerU 正是用此基准拿到开源第一的 95.69 分。GitHub: https://github.com/opendatalab/OmniDocBench

**DocLayNet** — IBM 发布的大规模版面分析数据集，80K 页，COCO 格式标注。主要评测 layout detection 的 mAP。适合作为版面分析专项评测。GitHub: https://github.com/DS4SD/DocLayNet

**PubLayNet** — IBM 发布，360K 页学术论文版面标注，规模更大但偏学术文档。GitHub: https://github.com/ibm-aur-nlp/PubLayNet

**PubTabNet / PubTables-1M** — 表格识别领域的标杆数据集。定义了 TEDS（Tree Edit Distance Similarity）指标，目前已被业界广泛采用，作为表格结构识别的标准评测方式。GitHub: https://github.com/ibm-aur-nlp/PubTabNet

**FinTabNet** — 金融文档表格识别数据集，适合评测复杂表格（合并单元格、多层表头等）。GitHub: https://github.com/ibm-aur-nlp/FinTabNet

**CDLA** — 中文文档版面分析数据集，5K 页中文文档标注。如果评测涉及中文文档，这是重要的补充。GitHub: https://github.com/buptLrqi/CDLA

**OCRBench v2** — NeurIPS 2025，全面的多模态 OCR 评测基准，覆盖文本识别、公式识别、表格识别、KIE 等。GitHub: https://github.com/Yuliang-Liu/MultimodalOCR

**DocBank** — 500K 页文档图像，弱监督标注，适合大规模版面分析评测。GitHub: https://github.com/doc-analysis/DocBank

---

### 二、专项评测工具（无自带数据集，需配合你自己的测试集）

#### 2.1 表格评测

**TEDS 指标**（Tree Edit Distance Similarity）是目前表格评测的事实标准，来自 PubTabNet 论文。计算方式是将表格转为 HTML 树后求编辑距离归一化分数。可直接在你的 newbench 测试集上使用。实现参考：
- https://github.com/ibm-aur-nlp/PubTabNet 中的 `teds.py`
- https://github.com/google-research/google-research 中的 TEDS 实现

#### 2.2 版面 / 阅读顺序评测

**LayoutParser** — 统一的版面分析工具包，支持多种检测模型和评测指标（mAP、IoU）。GitHub: https://github.com/Layout-Parser/layout-parser

**LayoutReader** — 专门评测阅读顺序（reading order）的工具。对你的 selected_layout 测试集特别有用。GitHub: https://github.com/microsoft/LayoutReader

#### 2.3 OCR / 文本保真度评测

**RapidFuzz / python-Levenshtein** — 高速编辑距离计算，适合批量评测文本保真度（CER/WER）。`pip install Levenshtein`，C++ 后端，处理数千文档很快。

**jiwer** — 专门的 WER/CER 计算库，API 简洁。`pip install jiwer`。

**difflib**（Python 内置）— `SequenceMatcher.ratio()` 零依赖快速基线。

#### 2.4 公式 / 图表评测

**UniMERNet** — 公式识别评测，CDM（Character Detection Match）指标。GitHub: https://github.com/wanderkid/UniMERNet

**ChartQA / mChartQA** — 图表理解评测基准。

---

### 三、Markdown 输出质量评测工具

这一类工具不是评测"转换准确率"，而是评测转换产出的 Markdown 文件本身的质量——格式是否规范、结构是否合理。可以直接用在你的转换 pipeline 的输出端。

#### 3.1 Markdown Lint 工具

**markdownlint (DavidAnson)** — 业界标准，60+ 条规则，覆盖标题层级、列表格式、代码块风格、表格格式、空行一致性等。Node.js，`npm install markdownlint-cli2`，支持 JSON 输出可程序化处理。GitHub: https://github.com/DavidAnson/markdownlint

**PyMarkdown** — Python 原生的 Markdown Linter，CommonMark + GFM 合规检查。`pip install pymarkdownlnt`，适合 Python pipeline。GitHub: https://github.com/jackdewinter/pymarkdown

**lint-md** — 基于 AST 的中文 Markdown Linter，可以检测中英文排版、标题层级跳跃等结构性问题。GitHub: https://github.com/lint-md/lint-md

**remark-lint** — 插件化架构，可以组合自定义规则集。`remark-validate-links` 插件可以检查链接有效性。GitHub: https://github.com/remarkjs/remark-lint

#### 3.2 Markdown 结构分析（AST 对比）

**markdown-it-py** — Python Markdown 解析器，产出 token stream（类似 AST）。可以解析"参考 Markdown"和"转换 Markdown"，对比节点数量、标题深度分布、表格维度等结构差异。`pip install markdown-it-py`。GitHub: https://github.com/executablebooks/markdown-it-py

**mistletoe** — 快速 Python Markdown AST 解析器，可以写自定义"质量评分渲染器"遍历 AST 产出指标。GitHub: https://github.com/miyuchina/mistletoe

#### 3.3 文档相似度对比

**TextDistance** — 提供 30+ 种距离/相似度算法（Levenshtein、Jaccard、Jaro-Winkler 等），纯 Python 零依赖。`pip install textdistance`。GitHub: https://github.com/life4/textdistance

**Google diff-match-patch** — 字符级 diff，多语言支持。可计算"转换准确率"（匹配字符数 / 总字符数）。`pip install diff-match-patch`。

#### 3.4 NLP 评测指标库

**HuggingFace Evaluate** — 统一接口提供 100+ 指标：BLEU、ROUGE、BERTScore、METEOR、CER、WER 等。`pip install evaluate`。把原文当 reference、转换 Markdown 当 prediction 即可计算。GitHub: https://github.com/huggingface/evaluate

**BERTScore** — 基于上下文 embedding 的语义相似度，不同于 BLEU/ROUGE 的表面 token 匹配，能捕捉"意思对但表述不同"的情况。`pip install bert-score`。CPU 偏慢，GPU 推荐。GitHub: https://github.com/Tiiiger/bert_score

**rouge-score** — Google 出品，ROUGE-1/2/L/S，特别适合文档转换评测：R1 衡量词汇保留、R2 衡量短语保留、RL 衡量序列保留。`pip install rouge-score`。

#### 3.5 专门针对 Markdown 转换质量的学术工具

**MDEval** — 来自论文（arXiv:2501.15000），最接近你需求的专用工具。方法：将 Markdown "HTML化"提取结构标签序列，然后计算 Levenshtein 距离，得到 0-1 归一化的结构质量分数。包含 20K 实例的无参考数据集（中英双语）。论文: https://arxiv.org/abs/2501.15000

---

### 四、主流转换工具的评测方法论参考

| 工具 | 评测方法 | 主要指标 |
|------|---------|---------|
| **MinerU** | OmniDocBench 多维度评测 | BLEU、TEDS、CDM、mAP、reading_order |
| **Marker** | 自建 benchmark，与 ground truth 对比 | BLEU、编辑距离、表格准确率、公式渲染 |
| **Docling** | DocLayNet + 自建评测 | mAP(layout)、TEDS(table)、reading order |
| **Nougat** | 学术文档专项评测 | Edit distance、BLEU、Markdown 结构匹配 |
| **GROBID** | 自标注学术文档集 | Header/Body/Metadata extraction F1 |

---

### 五、推荐评测体系架构

基于以上调研，建议构建以下**五层评测体系**：

```
┌─────────────────────────────────────────────────┐
│  Layer 5: 综合评分 (Composite Quality Index)     │
│  加权汇总各层指标，输出单一可比分数               │
├─────────────────────────────────────────────────┤
│  Layer 4: 语义保真度                             │
│  BERTScore / Sentence-Transformers              │
│  衡量"意思是否还在"                              │
├─────────────────────────────────────────────────┤
│  Layer 3: 内容保真度                             │
│  ROUGE-1/2/L, BLEU-4, CER/WER                  │
│  衡量"文字有没有丢/错"                           │
├─────────────────────────────────────────────────┤
│  Layer 2: 结构保真度                             │
│  AST对比(markdown-it-py) + TEDS(表格) +         │
│  MDEval方法论 + reading order                    │
│  衡量"结构是否对"                                │
├─────────────────────────────────────────────────┤
│  Layer 1: 格式质量                               │
│  markdownlint/PyMarkdown 规则检查                │
│  衡量"Markdown 写得规不规范"                      │
└─────────────────────────────────────────────────┘
```

**各层权重建议**（可根据实际场景调整）：

| 层 | 权重 | 核心工具 | 依赖 |
|----|------|---------|------|
| L1 格式质量 | 15% | PyMarkdown / markdownlint | 无 |
| L2 结构保真度 | 30% | markdown-it-py + TEDS + MDEval | Python |
| L3 内容保真度 | 30% | HuggingFace Evaluate (ROUGE/BLEU/CER) | Python |
| L4 语义保真度 | 15% | BERTScore / sentence-transformers | Python + 模型 |
| L5 综合评分 | — | 加权汇总 | — |

**按评测集分类的对应关系**：

| 你的测试集 | 重点评测层 | 推荐工具 |
|-----------|-----------|---------|
| selected_layout (87个) | L2 结构 + L3 内容 | AST对比 + ROUGE + reading order |
| selected_table (待建) | L2 结构 | TEDS (表格编辑距离) |
| selected_text (160个) | L3 内容 + L4 语义 | ROUGE + BLEU + BERTScore |

---

### 六、落地优先级建议

**第一优先级（Must-have，纯 Python，开箱即用）：**
1. `pip install evaluate` — HuggingFace Evaluate，一站式拿到 ROUGE/BLEU/CER/WER
2. `pip install markdown-it-py` — AST 结构对比
3. `pip install Levenshtein` — 高速编辑距离
4. `pip install pymarkdownlnt` — Markdown 格式规范检查

**第二优先级（Should-have，需要额外模型）：**
5. `pip install bert-score` — 语义相似度（CPU 可用但偏慢）
6. TEDS 指标实现（从 PubTabNet 仓库提取）— 表格专项评测

**第三优先级（Nice-to-have，扩展评测维度）：**
7. markdownlint-cli2 — 更丰富的格式规则（需要 Node.js）
8. MDEval 方法论复现 — Markdown 结构质量专用评分
9. sentence-transformers — 更精细的语义对比
