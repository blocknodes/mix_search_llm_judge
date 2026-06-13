#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键执行入口
用法:
    python run.py                                          # 默认跑 benchmark.csv
    python run.py --benchmark benchmark.csv --output result.jsonl  # 指定 benchmark 文件
    python run.py --query "你的问题" --category product    # 单条查询
    python run.py --workers 10                             # 指定并发数
    python run.py --shuffle                                # 随机打乱顺序后执行
    python run.py --shuffle --seed 123                     # 指定随机种子
"""
import argparse
import json
import logging
import os
import csv
import random
import tempfile
from pipeline import process_query, process_benchmark
from config import JUDGE_CONFIG

HIT_NS = JUDGE_CONFIG["hit_ns"]


def shuffle_benchmark(csv_file: str, seed: int = None) -> str:
    """读取 benchmark CSV，打乱顺序后写入临时文件，返回临时文件路径"""
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if seed is not None:
        random.seed(seed)
    random.shuffle(rows)

    # 写入临时文件（保留原始 CSV 的所有列）
    tmp_dir = os.path.dirname(csv_file) or '.'
    fd, tmp_path = tempfile.mkstemp(suffix='.csv', prefix='benchmark_shuffled_', dir=tmp_dir)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return tmp_path


def main():
    parser = argparse.ArgumentParser(description="混合检索 + LLM 相关性评分")
    parser.add_argument("--query", "-q", type=str, help="单条查询")
    parser.add_argument("--category", "-c", type=str, default="product",
                        choices=["product", "hr"], help="查询类别")
    parser.add_argument("--benchmark", "-b", type=str, help="benchmark CSV 文件路径")
    parser.add_argument("--output", "-o", type=str, help="输出文件路径")
    parser.add_argument("--top-k", type=int, default=None, help="检索返回数量 (默认使用config配置)")
    parser.add_argument("--judge-top-n", type=int, default=3, help="LLM评分数量")
    parser.add_argument("--workers", "-w", type=int, default=5, help="并发线程数")
    parser.add_argument("--shuffle", action="store_true", help="随机打乱 benchmark 顺序后执行")
    parser.add_argument("--seed", type=int, default=None, help="shuffle 随机种子")
    parser.add_argument("--source", "-s", type=str, default=None, help="按'问题来源'列过滤子集，如: --source 历史评测")
    parser.add_argument("--debug", action="store_true", help="开启 debug 模式，打印接口请求/响应日志")

    args = parser.parse_args()

    # 配置日志级别
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )

    if args.query:
        # 单条查询模式
        result = process_query(args.query, category=args.category,
                               top_k=args.top_k, judge_top_n=args.judge_top_n)
        print_result(result)

    else:
        # Benchmark 模式（默认）
        benchmark_file = args.benchmark or os.path.join(os.path.dirname(__file__), "benchmark.csv")
        output_file = args.output or os.path.join(os.path.dirname(__file__), "result.jsonl")

        if not os.path.exists(benchmark_file):
            print(f"错误: benchmark 文件不存在: {benchmark_file}")
            return

        # Shuffle 模式：打乱顺序后写入临时文件再执行
        actual_benchmark = benchmark_file
        if args.shuffle:
            actual_benchmark = shuffle_benchmark(benchmark_file, args.seed)
            print(f"Shuffle 模式: 已打乱顺序 (seed={args.seed})")

        print(f"Benchmark 模式: {benchmark_file} -> {output_file}")
        print(f"并发线程数: {args.workers}")
        if args.source:
            print(f"过滤问题来源: {args.source}")
        print()

        stats = process_benchmark(actual_benchmark, output_file, max_workers=args.workers,
                                  source_filter=args.source)

        # 清理临时文件
        if args.shuffle and actual_benchmark != benchmark_file:
            os.remove(actual_benchmark)

        print("\n" + "=" * 60)
        print("处理完成！统计信息:")
        print(f"  总数: {stats['total']}")
        for n in HIT_NS:
            key = f"hit{n}"
            if key in stats:
                print(f"  Hit@{n}: {stats[key]} ({stats.get(f'{key}_rate', 0):.2%})")
        print(f"  失败: {stats['failed']}")

        # 输出比率指标
        if stats["total"] > 0:
            ratios = []
            if "hit3" in stats and "hit6" in stats and stats["hit6"] > 0:
                ratios.append(f"  Hit@3/Hit@6: {stats['hit3']/stats['hit6']:.2%}")
            if "hit3" in stats and "hit10" in stats and stats["hit10"] > 0:
                ratios.append(f"  Hit@3/Hit@10: {stats['hit3']/stats['hit10']:.2%}")
            if ratios:
                print("\n比率指标:")
                for r in ratios:
                    print(r)

        print("\n按类别统计:")
        for cat, cat_stats in stats.get("by_category", {}).items():
            print(f"\n  [{cat}]")
            print(f"    总数: {cat_stats['total']}")
            for n in HIT_NS:
                key = f"hit{n}"
                if key in cat_stats:
                    print(f"    Hit@{n}: {cat_stats[key]} ({cat_stats.get(f'{key}_rate', 0):.2%})")
            print(f"    失败: {cat_stats['failed']}")


def print_result(result):
    """打印结果"""
    if not result:
        print("处理失败")
        return

    print("\n" + "=" * 50)
    print(f"查询: {result['query']}")
    print(f"类别: {result.get('category', 'N/A')}")
    for n in HIT_NS:
        key = f"hit{n}"
        if key in result:
            print(f"Hit@{n}: {result[key]}")
    print("\n候选结果:")

    for i, item in enumerate(result.get('candidates', [])):
        print(f"\n[{i+1}] 文件: {item.get('filename', 'N/A')}")
        print(f"    检索分数: {item.get('score', 0):.4f}")
        print(f"    LLM相关性: {item.get('llm_relevance', 'N/A')}")
        content = item.get('content', '')
        print(f"    内容: {content[:100]}..." if len(content) > 100 else f"    内容: {content}")


if __name__ == "__main__":
    main()
