#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Server API 模式 (FastAPI) - 提供 HTTP 接口进行检索 + LLM 评分

启动:
    uvicorn server:app --host 0.0.0.0 --port 8080 --workers 1
    python server.py --port 8080
"""
import argparse
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel

from kbp_client import KbpRetrievalClient
from llm_client import LLMClient
from pipeline import process_query, stage1_retrieve, stage2_judge
from config import CONCURRENCY_CONFIG, JUDGE_CONFIG

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="检索质量评估 API")

# 全局线程池
executor: ThreadPoolExecutor = None


class QueryRequest(BaseModel):
    query: str
    category: str = "product"
    top_k: Optional[int] = None
    judge_top_n: Optional[int] = None
    user_key: Optional[str] = None
    api_key: Optional[str] = None


class BatchRequest(BaseModel):
    queries: List[QueryRequest]
    top_k: Optional[int] = None
    judge_top_n: Optional[int] = None
    user_key: Optional[str] = None
    api_key: Optional[str] = None


@app.on_event("startup")
def startup():
    global executor
    executor = ThreadPoolExecutor(max_workers=CONCURRENCY_CONFIG["max_workers"])


@app.on_event("shutdown")
def shutdown():
    executor.shutdown(wait=False)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {elapsed:.0f}ms")
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
async def query_single(req: QueryRequest):
    """
    单条查询：检索 + LLM 评分

    可选传入 user_key / api_key 覆盖默认配置
    """
    logger.info(f"[/query] query=\"{req.query[:50]}\" category={req.category}")
    loop = asyncio.get_event_loop()

    user_key = req.user_key
    api_key = req.api_key

    result = await loop.run_in_executor(
        executor,
        lambda: process_query(
            query=req.query,
            category=req.category,
            kbp_client=KbpRetrievalClient(user_key=user_key, api_key=api_key),
            llm_client=LLMClient(),
            top_k=req.top_k,
            judge_top_n=req.judge_top_n
        )
    )

    if result is None:
        logger.warning(f"[/query] 处理失败: query=\"{req.query[:50]}\"")
        return {"error": "处理失败"}

    hit_log = " ".join(f"hit{n}={result.get(f'hit{n}')}" for n in JUDGE_CONFIG["hit_ns"])
    logger.info(f"[/query] 完成: {hit_log}")
    return result


class RetrieveRequest(BaseModel):
    query: str
    category: str = "product"
    top_k: Optional[int] = None
    score_threshold: Optional[float] = None
    search_mode: Optional[str] = None
    search_strategy: Optional[str] = None
    user_key: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    retrieval_path: Optional[str] = None


class JudgeRequest(BaseModel):
    query: str
    category: str = "product"
    candidates: List[dict]
    judge_top_n: Optional[int] = None


@app.post("/retrieve")
async def retrieve(req: RetrieveRequest):
    """
    第一阶段：仅调用 KBP 检索，返回候选结果（不评分）
    """
    logger.info(f"[/retrieve] query=\"{req.query[:50]}\" category={req.category}")
    loop = asyncio.get_event_loop()

    user_key = req.user_key
    api_key = req.api_key

    result = await loop.run_in_executor(
        executor,
        lambda: stage1_retrieve(
            query=req.query,
            category=req.category,
            kbp_client=KbpRetrievalClient(
                user_key=user_key, api_key=api_key,
                base_url=req.base_url, retrieval_path=req.retrieval_path
            ),
            top_k=req.top_k,
            score_threshold=req.score_threshold,
            search_mode=req.search_mode,
            search_strategy=req.search_strategy
        )
    )

    if result is None:
        logger.warning(f"[/retrieve] 检索失败: query=\"{req.query[:50]}\"")
        return {"error": "检索失败"}

    logger.info(f"[/retrieve] 完成: {len(result.get('candidates', []))} 条候选")
    return result


@app.post("/judge")
async def judge(req: JudgeRequest):
    """
    第二阶段：对已有候选结果进行 LLM 相关性评分

    输入为 /retrieve 的输出（或自行构造的 candidates）
    """
    logger.info(f"[/judge] query=\"{req.query[:50]}\" candidates={len(req.candidates)}")
    loop = asyncio.get_event_loop()

    retrieval_result = {
        "query": req.query,
        "category": req.category,
        "candidates": req.candidates
    }

    result = await loop.run_in_executor(
        executor,
        lambda: stage2_judge(
            retrieval_result=retrieval_result,
            judge_top_n=req.judge_top_n
        )
    )

    if result is None:
        logger.warning(f"[/judge] 评分失败: query=\"{req.query[:50]}\"")
        return {"error": "评分失败"}

    hit_log = " ".join(f"hit{n}={result.get(f'hit{n}')}" for n in JUDGE_CONFIG["hit_ns"])
    logger.info(f"[/judge] 完成: {hit_log}")
    return result


class BatchJudgeRequest(BaseModel):
    items: List[JudgeRequest]
    judge_top_n: Optional[int] = None


@app.post("/judge/batch")
async def judge_batch(req: BatchJudgeRequest):
    """
    第二阶段批量：对多条检索结果进行 LLM 评分，返回结果 + stats

    输入为多个 /retrieve 的输出
    """
    logger.info(f"[/judge/batch] 收到 {len(req.items)} 条")
    loop = asyncio.get_event_loop()

    judge_top_n = req.judge_top_n

    def judge_one(item: JudgeRequest):
        retrieval_result = {
            "query": item.query,
            "category": item.category,
            "candidates": item.candidates
        }
        return stage2_judge(
            retrieval_result=retrieval_result,
            judge_top_n=judge_top_n or item.judge_top_n
        )

    futures = [
        loop.run_in_executor(executor, judge_one, item)
        for item in req.items
    ]
    results_raw = await asyncio.gather(*futures)

    results = []
    hit_ns = JUDGE_CONFIG["hit_ns"]
    stats = {"total": len(req.items), "failed": 0}
    for n in hit_ns:
        stats[f"hit{n}"] = 0

    for result in results_raw:
        if result:
            results.append(result)
            for n in hit_ns:
                if result.get(f"hit{n}"):
                    stats[f"hit{n}"] += 1
        else:
            stats["failed"] += 1

    if stats["total"] > 0:
        for n in hit_ns:
            stats[f"hit{n}_rate"] = f"{stats[f'hit{n}']/stats['total']:.2%}"

    hit_log = " ".join(f"hit{n}={stats[f'hit{n}']}" for n in hit_ns)
    logger.info(f"[/judge/batch] 完成: total={stats['total']} {hit_log} failed={stats['failed']}")
    return {"results": results, "stats": stats}


@app.post("/batch")
async def query_batch(req: BatchRequest):
    """
    批量查询

    可选传入 user_key / api_key 覆盖默认配置（全局或每条单独指定）
    """
    logger.info(f"[/batch] 收到 {len(req.queries)} 条查询")
    loop = asyncio.get_event_loop()

    top_k = req.top_k
    judge_top_n = req.judge_top_n
    global_user_key = req.user_key
    global_api_key = req.api_key

    def process_one(item: QueryRequest):
        user_key = item.user_key or global_user_key
        api_key = item.api_key or global_api_key
        return process_query(
            query=item.query,
            category=item.category,
            kbp_client=KbpRetrievalClient(user_key=user_key, api_key=api_key),
            llm_client=LLMClient(),
            top_k=top_k or item.top_k,
            judge_top_n=judge_top_n or item.judge_top_n
        )

    futures = [
        loop.run_in_executor(executor, process_one, item)
        for item in req.queries
    ]
    results_raw = await asyncio.gather(*futures)

    results = []
    hit_ns = JUDGE_CONFIG["hit_ns"]
    stats = {"total": len(req.queries), "failed": 0}
    for n in hit_ns:
        stats[f"hit{n}"] = 0

    for result in results_raw:
        if result:
            results.append(result)
            for n in hit_ns:
                if result.get(f"hit{n}"):
                    stats[f"hit{n}"] += 1
        else:
            stats["failed"] += 1

    if stats["total"] > 0:
        for n in hit_ns:
            stats[f"hit{n}_rate"] = f"{stats[f'hit{n}']/stats['total']:.2%}"

    hit_log = " ".join(f"hit{n}={stats[f'hit{n}']}" for n in hit_ns)
    logger.info(f"[/batch] 完成: total={stats['total']} {hit_log} failed={stats['failed']}")
    return {"results": results, "stats": stats}


def main():
    parser = argparse.ArgumentParser(description="检索评估 Server API (FastAPI)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", "-p", type=int, default=8080, help="端口号")
    parser.add_argument("--workers", "-w", type=int, default=1, help="uvicorn worker 数")
    args = parser.parse_args()

    print(f"Server 启动: http://{args.host}:{args.port}")
    print(f"API 文档: http://{args.host}:{args.port}/docs")

    uvicorn.run("server:app", host=args.host, port=args.port, workers=args.workers)


if __name__ == "__main__":
    main()
