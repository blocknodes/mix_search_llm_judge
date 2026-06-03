#!/usr/bin/env python3
"""将 result.jsonl 转换为 CSV 格式。

每条 candidate 展开为一行，包含 query 级别的字段和 candidate 级别的字段。
"""

import json
import csv
import sys
import re
from pathlib import Path


def clean_content(text: str) -> str:
    """清理 content 字段：去除换行、markdown 表格符号、多余空格等"""
    if not text:
        return ""
    # 换行替换为空格
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    # 去掉 markdown 表格分隔线（如 ---|---|---）
    text = re.sub(r"-{2,}(\|-{2,})+", " ", text)
    # 把 | 替换为空格（避免被 Excel/WPS 误认为分隔符）
    text = text.replace("|", " ")
    # 压缩连续空格
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def main():
    input_file = Path("result.jsonl")
    output_file = Path("result.csv")

    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_file = Path(sys.argv[2])

    rows = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)

            query = record.get("query", "")
            category = record.get("category", "")
            hit1 = record.get("hit1", "")
            hit3 = record.get("hit3", "")
            hit6 = record.get("hit6", "")
            hit10 = record.get("hit10", "")

            candidates = record.get("candidates", [])
            # 每个 candidate 压缩到对应列：candidate_1_title, candidate_1_score, ...
            row = {
                "query": query,
                "category": category,
                "hit1": hit1,
                "hit3": hit3,
                "hit6": hit6,
                "hit10": hit10,
            }
            for i, cand in enumerate(candidates):
                prefix = f"candidate_{i+1}"
                row[f"{prefix}_kind"] = cand.get("kind", "")
                row[f"{prefix}_filename"] = cand.get("filename", "")
                row[f"{prefix}_title"] = cand.get("title", "")
                row[f"{prefix}_content"] = clean_content(cand.get("content", ""))
                row[f"{prefix}_category_path"] = cand.get("category_path", "")
                row[f"{prefix}_score"] = cand.get("score", "")
                row[f"{prefix}_llm_relevance"] = cand.get("llm_relevance", "")
            rows.append(row)

    if not rows:
        print("No data found.")
        return

    # 收集所有可能的列名（不同行 candidate 数量可能不同）
    fieldnames = []
    seen = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                fieldnames.append(k)
                seen.add(k)

    with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done! {len(rows)} rows written to {output_file}")


if __name__ == "__main__":
    main()
