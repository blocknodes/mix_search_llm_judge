#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统计 result.jsonl 中的 Hit@N 指标，支持自定义 N 值

用法:
    python stats.py                          # 默认统计 hit@1, hit@3, hit@10
    python stats.py --hit 1 3 5 10           # 自定义统计 hit@1, hit@3, hit@5, hit@10
    python stats.py --input result.jsonl --hit 1 5 20
    python stats.py --threshold 7            # 自定义相关性阈值 (默认8)
"""
import argparse
import json
import os
from collections import defaultdict
from typing import List


def compute_stats(input_file: str, hit_ns: List[int] = None, threshold: int = 8):
    """
    统计 result.jsonl 中的 hit@n
    
    根据 candidates 中的 llm_relevance 分数重新计算 hit@n，
    支持任意 n 值。
    """
    hit_ns = hit_ns or [1, 3, 10]
    hit_ns = sorted(hit_ns)

    total = 0
    failed = 0
    by_category = defaultdict(lambda: {"total": 0, **{f"hit{n}": 0 for n in hit_ns}})
    overall = {"total": 0, **{f"hit{n}": 0 for n in hit_ns}}

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                failed += 1
                continue

            total += 1
            cat = data.get("category", "unknown")
            cat_stats = by_category[cat]
            cat_stats["total"] += 1
            overall["total"] += 1

            # 从 candidates 的 llm_relevance 重新计算 hit@n
            candidates = data.get("candidates", [])
            for n in hit_ns:
                hit = False
                for item in candidates[:n]:
                    if item.get("llm_relevance", 0) >= threshold:
                        hit = True
                        break
                if hit:
                    cat_stats[f"hit{n}"] += 1
                    overall[f"hit{n}"] += 1

    # 打印结果
    print(f"文件: {input_file}")
    print(f"总条数: {total}")
    print(f"相关性阈值: >= {threshold}")
    if failed:
        print(f"解析失败: {failed}")

    print(f"\n{'='*60}")
    header = f"{'指标':<12} {'命中数':<10} {'比率':<10}"
    print(header)
    print(f"{'-'*60}")
    if overall["total"] > 0:
        for n in hit_ns:
            key = f"hit{n}"
            print(f"{'Hit@'+str(n):<12} {overall[key]:<10} {overall[key]/overall['total']:.2%}")

    if len(by_category) > 1:
        print(f"\n{'='*60}")
        print("按类别统计:")
        for cat, stats in sorted(by_category.items()):
            t = stats["total"]
            print(f"\n  [{cat}] (共 {t} 条)")
            for n in hit_ns:
                key = f"hit{n}"
                print(f"    Hit@{n:<4} {stats[key]:>4} / {t}  = {stats[key]/t:.2%}")


def main():
    parser = argparse.ArgumentParser(description="统计 result.jsonl 中的 Hit@N")
    parser.add_argument("--input", "-i", type=str, default="result.jsonl", help="输入文件")
    parser.add_argument("--hit", "-n", nargs='+', type=int, default=[1, 3, 10],
                        help="要统计的 Hit@N 值 (默认: 1 3 10)")
    parser.add_argument("--threshold", "-t", type=int, default=8,
                        help="相关性得分阈值 (默认: 8)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = args.input if os.path.isabs(args.input) else os.path.join(script_dir, args.input)

    if not os.path.exists(input_file):
        print(f"错误: 文件不存在: {input_file}")
        return

    compute_stats(input_file, args.hit, args.threshold)


if __name__ == "__main__":
    main()
