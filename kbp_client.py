"""
KBP 混合检索客户端
"""
import requests
import json
import random
import time
import logging
from typing import Dict, Optional

from config import (KBP_BASE_URL, KBP_USER_KEY, KBP_RETRIEVAL_PATH,
                    KBP_API_KEY, RETRIEVAL_CONFIG, RETRY_CONFIG)

logger = logging.getLogger(__name__)


class KbpRetrievalClient:
    """封装 KBP 混合检索 API 的客户端类"""

    def __init__(self, user_key: str = None, api_key: str = None,
                 base_url: str = None, retrieval_path: str = None):
        self.base_url = (base_url or KBP_BASE_URL).rstrip('/')
        self.user_key = user_key or KBP_USER_KEY
        self.api_key = api_key or KBP_API_KEY
        self.retrieval_path = retrieval_path or KBP_RETRIEVAL_PATH
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'api-key': self.api_key
        })

        # 从配置加载重试参数
        self.retry_config = RETRY_CONFIG["kbp"]

    def retrieval(self, query: str, top_k: int = None, score_threshold: float = None,
                  search_mode: str = None, search_strategy: str = None,
                  tracing_model: bool = None,
                  max_retries: int = None, initial_delay: float = None,
                  backoff_factor: float = None) -> Optional[Dict]:
        """
        执行检索请求（带退火重试机制）
        """
        top_k = top_k or RETRIEVAL_CONFIG["top_k"]
        score_threshold = score_threshold if score_threshold is not None else RETRIEVAL_CONFIG["score_threshold"]
        search_mode = search_mode or RETRIEVAL_CONFIG["search_mode"]
        search_strategy = search_strategy or RETRIEVAL_CONFIG["search_strategy"]
        tracing_model = tracing_model if tracing_model is not None else RETRIEVAL_CONFIG["tracing_model"]

        # 使用配置的重试参数
        max_retries = max_retries if max_retries is not None else self.retry_config["max_retries"]
        initial_delay = initial_delay if initial_delay is not None else self.retry_config["initial_delay"]
        backoff_factor = backoff_factor if backoff_factor is not None else self.retry_config["backoff_factor"]
        jitter_ratio = self.retry_config["jitter_ratio"]

        url = f"{self.base_url}{self.retrieval_path}?user_key={self.user_key}"
        logger.info(f"[KBP] 请求 URL: {url}")

        payload = {
            "query": query,
            "retrieval_setting": {
                "top_k": top_k,
                "score_threshold": score_threshold,
                "search_mode": search_mode,
                "search_strategy": search_strategy,
            },
            "tracingModel": tracing_model
        }

        for attempt in range(max_retries + 1):
            try:
                response = self.session.post(url, data=json.dumps(payload))
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    delay = initial_delay * (backoff_factor ** attempt)
                    delay += random.uniform(0, jitter_ratio * delay)
                    logger.warning(f"KBP请求失败（第 {attempt+1}/{max_retries} 次）: {e}，{delay:.1f}s 后重试")
                    time.sleep(delay)
                else:
                    logger.error(f"KBP最终失败（已重试 {max_retries} 次）: {e}")

        return None
