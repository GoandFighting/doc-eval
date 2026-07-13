"""
filter_jsonl.py
根据 newbench 子文件夹中选中的文件，精简 parsebench_data 下的 JSONL 标注文件。

映射关系（一一对应）:
  selected_layout/ → layout.jsonl
  selected_table/  → table.jsonl
  selected_text/   → text_content.jsonl + text_formatting.jsonl
"""

import json
import os

# ---------- 路径配置 ----------
SRC_DIR = r"C:\tiqu\parsebench_data"
DST_DIR = r"C:\tiqu\newbench"

# 文件夹 → 对应的 JSONL 文件列表（一一映射）
FOLDER_TO_JSONLS = {
    "selected_layout": ["layout.jsonl"],
    "selected_table":  ["table.jsonl"],
    "selected_text":   ["text_content.jsonl", "text_formatting.jsonl"],
}


def collect_filenames(folder_path: str) -> set[str]:
    """收集文件夹中所有文件名（不含路径前缀）。"""
    return set(os.listdir(folder_path))


def filter_jsonl(src_path: str, keep_names: set[str]) -> list[dict]:
    """读取 JSONL，只保留 pdf 字段文件名在 keep_names 中的记录。"""
    kept = []
    with open(src_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # pdf 字段格式: docs/{category}/{filename}
            fname = rec["pdf"].rsplit("/", 1)[-1]
            if fname in keep_names:
                kept.append(rec)
    return kept


def write_jsonl(records: list[dict], dst_path: str) -> None:
    with open(dst_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    # 1. 按文件夹收集文件名
    name_sets: dict[str, set[str]] = {}
    for folder in FOLDER_TO_JSONLS:
        folder_path = os.path.join(DST_DIR, folder)
        if not os.path.isdir(folder_path):
            print(f"[WARN] 文件夹不存在，跳过: {folder_path}")
            continue
        name_sets[folder] = collect_filenames(folder_path)
        print(f"[INFO] {folder}/ 共 {len(name_sets[folder])} 个文件")

    # 2. 逐个 JSONL 过滤
    print()
    total_kept = 0
    for folder, jsonl_names in FOLDER_TO_JSONLS.items():
        if folder not in name_sets:
            continue
        keep = name_sets[folder]

        for jname in jsonl_names:
            src = os.path.join(SRC_DIR, jname)
            if not os.path.isfile(src):
                print(f"[WARN] 源文件不存在，跳过: {src}")
                continue

            kept = filter_jsonl(src, keep)
            dst = os.path.join(DST_DIR, jname)
            write_jsonl(kept, dst)

            # 统计原始行数
            with open(src, encoding="utf-8") as f:
                orig = sum(1 for line in f if line.strip())

            total_kept += len(kept)
            print(f"[OK] {jname}: {orig} → {len(kept)} 条记录  (精简 {orig - len(kept)} 条)")

    print(f"\n[完成] 共保留 {total_kept} 条记录，输出目录: {DST_DIR}")


if __name__ == "__main__":
    main()
