"""
一键执行的 Pipeline：混合检索 + LLM 相关性评分
"""
import csv
import json
import logging
import sys
import time
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from kbp_client import KbpRetrievalClient
from llm_client import LLMClient
from llm_judge import judge_relevance, compute_hit_metrics
from config import JUDGE_CONFIG, CONCURRENCY_CONFIG

logger = logging.getLogger(__name__)

# 线程本地存储，避免多线程共享客户端
_thread_local = threading.local()

# 从配置读取 hit_ns
HIT_NS = JUDGE_CONFIG["hit_ns"]


def print_progress(processed, total, stats, start_time):
    """打印进度条（含时间）"""
    import time
    bar_len = 30
    filled = int(bar_len * processed / total) if total > 0 else 0
    bar = '█' * filled + '░' * (bar_len - filled)
    pct = processed / total * 100 if total > 0 else 0

    elapsed = time.time() - start_time
    if processed > 0:
        eta = elapsed / processed * (total - processed)
        eta_str = f"{int(eta//60)}m{int(eta%60)}s"
    else:
        eta_str = "--"
    elapsed_str = f"{int(elapsed//60)}m{int(elapsed%60)}s"

    hit_parts = " ".join(f"H@{n}:{stats[f'hit{n}']}" for n in HIT_NS)
    sys.stdout.write(
        f"\r[{bar}] {processed}/{total} ({pct:.1f}%) "
        f"| {elapsed_str}<{eta_str} "
        f"| {hit_parts} F:{stats['failed']}"
    )
    sys.stdout.flush()
    if processed == total:
        sys.stdout.write('\n')


def stage1_retrieve(query: str, category: str = "product",
                    kbp_client: KbpRetrievalClient = None,
                    top_k: int = None, score_threshold: float = None,
                    search_mode: str = None, search_strategy: str = None,
                    api_key: str = None) -> Optional[Dict]:
    """
    第一阶段：调用 KBP 检索

    Returns:
        {"query": ..., "category": ..., "candidates": [...]}
    """
    if kbp_client is None:
        kbp_client = KbpRetrievalClient()

    # 如果该 query 有自己的 api_key，临时替换
    original_api_key = None
    if api_key:
        original_api_key = kbp_client.api_key
        kbp_client.api_key = api_key
        kbp_client.session.headers['api-key'] = api_key

    retrieval_result = kbp_client.retrieval(
        query=query, top_k=top_k,
        score_threshold=score_threshold,
        search_mode=search_mode,
        search_strategy=search_strategy
    )

    # 恢复原始 api_key
    if original_api_key is not None:
        kbp_client.api_key = original_api_key
        kbp_client.session.headers['api-key'] = original_api_key

    if retrieval_result is None:
        return None

    finals = retrieval_result.get('records', [])
    if not finals:
        return {"query": query, "category": category, "candidates": []}

    candidates = [{
        'kind': (item.get('metadata') or {}).get('kind', ''),
        'filename': item.get('file_name', ''),
        'title': item.get('title', ''),
        'content': item.get('content', ''),
        'category_path': item.get('category_path', ''),
        'score': item.get('score', 0)
    } for item in finals]

    return {
        "query": query,
        "category": category,
        "candidates": candidates
    }


def stage2_judge(retrieval_result: Dict, llm_client: LLMClient = None,
                 judge_top_n: int = None) -> Optional[Dict]:
    """
    第二阶段：调用 LLM 进行相关性评分

    Args:
        retrieval_result: stage1_retrieve 的输出

    Returns:
        带有 llm_relevance 评分和 hit 指标的完整结果
    """
    if llm_client is None:
        llm_client = LLMClient()

    judge_top_n = judge_top_n or JUDGE_CONFIG["top_n"]

    query = retrieval_result["query"]
    category = retrieval_result.get("category", "product")
    candidates = retrieval_result.get("candidates", [])

    if not candidates:
        hit_metrics = {f"hit{n}": False for n in HIT_NS}
        return {"query": query, "category": category, "candidates": [], **hit_metrics}

    # LLM 相关性评分
    candidates = judge_relevance(query, candidates, llm_client, judge_top_n)

    # 计算 hit 指标
    hit_metrics = compute_hit_metrics(candidates)

    return {
        "query": query,
        "category": category,
        "candidates": candidates[:judge_top_n],
        **hit_metrics
    }


def process_query(query: str, category: str = "product",
                  kbp_client: KbpRetrievalClient = None,
                  llm_client: LLMClient = None, top_k: int = None,
                  judge_top_n: int = None, api_key: str = None) -> Optional[Dict]:
    """
    完整处理：检索 + LLM 评分（两阶段合并）
    """
    logger.debug(f"[Pipeline] query: {query}, apikey: {api_key or '(默认)'}")

    # Stage 1
    retrieval_result = stage1_retrieve(query, category, kbp_client, top_k,
                                       api_key=api_key)
    if retrieval_result is None:
        return None

    # Stage 2
    return stage2_judge(retrieval_result, llm_client, judge_top_n)


def load_benchmark_csv(csv_file: str, source_filter: str = None) -> List[Tuple[str, str, str]]:
    """从 benchmark.csv 读取查询、类别和 apikey，可按问题来源过滤"""
    queries = []
    with open(csv_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            query = row.get('query', '').strip()
            category = row.get('cat', '').strip() or "product"
            api_key = row.get('apikey', '').strip()
            source = row.get('问题来源', '').strip()
            if query:
                if source_filter and source != source_filter:
                    continue
                queries.append((query, category, api_key))
    return queries


def process_benchmark(input_file: str, output_file: str,
                      max_workers: int = None, source_filter: str = None) -> Dict:
    """批量处理 benchmark.csv（支持多线程）"""
    max_workers = max_workers or CONCURRENCY_CONFIG["max_workers"]

    # 读取 benchmark
    queries = load_benchmark_csv(input_file, source_filter=source_filter)
    total = len(queries)
    start_time = time.time()

    stats = {
        "total": total, "failed": 0, "processed": 0,
        "by_category": {}
    }
    for n in HIT_NS:
        stats[f"hit{n}"] = 0
    stats_lock = threading.Lock()

    def process_single(query: str, category: str, idx: int, api_key: str = "") -> Optional[Dict]:
        """处理单条查询的线程函数"""
        if not hasattr(_thread_local, 'kbp_client'):
            _thread_local.kbp_client = KbpRetrievalClient()
        if not hasattr(_thread_local, 'llm_client'):
            _thread_local.llm_client = LLMClient()

        try:
            result = process_query(
                query,
                category=category,
                kbp_client=_thread_local.kbp_client,
                llm_client=_thread_local.llm_client,
                api_key=api_key or None
            )
            return result
        except Exception as e:
            return None

    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(process_single, query, category, idx, api_key): (idx, query, category)
            for idx, (query, category, api_key) in enumerate(queries, 1)
        }

        for future in as_completed(future_to_idx):
            idx, query, category = future_to_idx[future]
            result = future.result()

            with stats_lock:
                stats["processed"] += 1

                if category not in stats["by_category"]:
                    stats["by_category"][category] = {"total": 0, "failed": 0}
                    for n in HIT_NS:
                        stats["by_category"][category][f"hit{n}"] = 0
                cat_stats = stats["by_category"][category]
                cat_stats["total"] += 1

                if result:
                    results.append((idx, result))
                    for n in HIT_NS:
                        key = f"hit{n}"
                        if result.get(key):
                            stats[key] += 1
                            cat_stats[key] += 1
                else:
                    stats["failed"] += 1
                    cat_stats["failed"] += 1

                print_progress(stats["processed"], total, stats, start_time)

    # 按原始顺序排序并写入文件
    results.sort(key=lambda x: x[0])
    with open(output_file, 'w', encoding='utf-8') as f:
        for _, result in results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')

    # 计算比率
    if stats["total"] > 0:
        for n in HIT_NS:
            stats[f"hit{n}_rate"] = stats[f"hit{n}"] / stats["total"]

    for cat, cat_stats in stats["by_category"].items():
        if cat_stats["total"] > 0:
            for n in HIT_NS:
                cat_stats[f"hit{n}_rate"] = cat_stats[f"hit{n}"] / cat_stats["total"]

    return stats
