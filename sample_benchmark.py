#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
对 benchmark.csv 按 category 进行采样

用法:
    python sample_benchmark.py                          # 默认: product=100%, hr=10%
    python sample_benchmark.py --ratio hr=0.1           # hr 采样 10%
    python sample_benchmark.py --ratio hr=0.1 product=0.5  # hr 10%, product 50%
    python sample_benchmark.py --ratio hr=20 product=100   # hr 取 20 条, product 取 100 条 (整数表示条数)
"""
import argparse
import csv
import random
import os
from collections import defaultdict
from typing import Dict, List


def parse_ratios(ratio_args: List[str]) -> Dict[str, float]:
    """
    解析比例参数
    格式: cat=ratio 或 cat=count
    - 0-1 之间的小数表示比例
    - >1 的整数表示具体条数
    """
    ratios = {}
    if not ratio_args:
        return ratios
    
    for item in ratio_args:
        if '=' not in item:
            continue
        cat, value = item.split('=', 1)
        ratios[cat.strip()] = float(value.strip())
    
    return ratios


def sample_benchmark(input_file: str, output_file: str, 
                     ratios: Dict[str, float] = None, seed: int = 42):
    """
    对 benchmark 按 category 进行采样
    
    Args:
        input_file: 输入 CSV 文件
        output_file: 输出 CSV 文件
        ratios: {category: ratio} 字典，ratio <= 1 表示比例，> 1 表示条数
        seed: 随机种子
    """
    random.seed(seed)
    ratios = ratios or {}
    
    # 按 category 分组
    rows_by_cat = defaultdict(list)
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            query = row.get('query', '').strip()
            cat = row.get('cat', '').strip()
            if not query or not cat:
                continue
            rows_by_cat[cat].append(row)
    
    # 采样
    sampled_rows = []
    print("采样结果:")
    
    for cat, rows in rows_by_cat.items():
        original_count = len(rows)
        ratio = ratios.get(cat, 1.0)  # 默认保留全部
        
        if ratio > 1:
            # 整数表示具体条数
            sample_size = min(int(ratio), original_count)
        else:
            # 小数表示比例
            sample_size = max(1, int(original_count * ratio))
        
        if sample_size >= original_count:
            sampled = rows
        else:
            sampled = random.sample(rows, sample_size)
        
        sampled_rows.extend(sampled)
        
        ratio_display = f"{ratio:.0%}" if ratio <= 1 else f"{int(ratio)} 条"
        print(f"  {cat}: {original_count} -> {len(sampled)} 条 ({ratio_display})")
    
    # 写入
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['query', 'cat'])
        writer.writeheader()
        writer.writerows(sampled_rows)
    
    print(f"\n总计: {sum(len(rows) for rows in rows_by_cat.values())} -> {len(sampled_rows)} 条")
    print(f"输出: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="对 benchmark 按 category 进行采样",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python sample_benchmark.py --ratio hr=0.1              # hr 采样 10%
  python sample_benchmark.py --ratio hr=0.1 product=0.5  # hr 10%, product 50%
  python sample_benchmark.py --ratio hr=20               # hr 取 20 条
        """
    )
    parser.add_argument("--input", "-i", type=str, default="benchmark.csv", help="输入文件")
    parser.add_argument("--output", "-o", type=str, default="benchmark_sampled.csv", help="输出文件")
    parser.add_argument("--ratio", "-r", nargs='+', default=["hr=0.1"], 
                        help="采样比例，格式: cat=ratio (0-1为比例, >1为条数)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    
    args = parser.parse_args()
    
    # 处理相对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = args.input if os.path.isabs(args.input) else os.path.join(script_dir, args.input)
    output_file = args.output if os.path.isabs(args.output) else os.path.join(script_dir, args.output)
    
    ratios = parse_ratios(args.ratio)
    sample_benchmark(input_file, output_file, ratios, args.seed)


if __name__ == "__main__":
    main()
