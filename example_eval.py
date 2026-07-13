"""示例：如何评测一个 PDF 转换结果。

使用方式：
    # 评测一个 md 文件
    python example_eval.py 转换结果.md text_simple__10k.pdf

    # 不带参数则跑一个内置演示（用 expected_markdown 模拟满分）
    python example_eval.py
"""

import asyncio
import sys
from pathlib import Path

from eval.core.config import EvalConfig
from eval.core.models import EvalRequest
from eval.core.runner import AsyncEvalRunner
from eval.report import print_summary, to_json


async def main():
    # ── 初始化评测器 ──
    config = EvalConfig(
        dataset_dir=Path("newbench"),
        enable_l1=True,
        enable_l4=False,
    )
    runner = AsyncEvalRunner(config)

    if len(sys.argv) >= 3:
        # 命令行模式：python example_eval.py <md文件> <pdf文件名>
        md_path = sys.argv[1]
        pdf_name = sys.argv[2]
        converted_md = Path(md_path).read_text(encoding="utf-8")
    else:
        # 演示模式：用 expected_markdown 模拟满分
        pdf_name = "1 timetable (1)_page27.pdf"
        test_cases = runner._parsebench._test_cases.get(pdf_name, [])
        converted_md = ""
        for tc in test_cases:
            if tc.expected_markdown:
                converted_md = tc.expected_markdown
                break
        if not converted_md:
            converted_md = "# 转换后的标题\n\n这是一段转换后的文本内容。\n"
        print(f"[演示模式] 用 {pdf_name} 的 expected_markdown 模拟转换结果")
        print("[实际使用] python example_eval.py 转换结果.md 对应的pdf文件名.pdf")
        print()

    # ── 执行评测 ──
    request = EvalRequest(converted_md=converted_md, pdf_name=pdf_name)
    response = await runner.evaluate(request)

    # ── 输出结果 ──
    print("=" * 60)
    print(print_summary(response))
    print("=" * 60)
    print()
    print("各维度分数:")
    for d in response.dimensions:
        print(f"  {d.dimension:25s}  {d.score:6.1f}  来源: {d.metadata.get('source', '自实现')}")
        for k, v in d.metrics.items():
            print(f"    └─ {k:30s} = {v:.4f}")
    print()
    print("完整 JSON:")
    print(to_json(response))


if __name__ == "__main__":
    asyncio.run(main())
