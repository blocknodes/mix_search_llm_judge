"""
LLM 客户端
"""
import requests
import json
import random
import time
import logging
import urllib3
from typing import Dict, List, Optional

from config import LLM_CONFIGS, DEFAULT_LLM, RETRY_CONFIG

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 客户端，支持自动重试"""

    def __init__(self, llm_configs: Dict = None, default_llm: str = None):
        self.llm_configs = llm_configs or LLM_CONFIGS
        self.default_llm = default_llm or DEFAULT_LLM

        if self.default_llm not in self.llm_configs:
            raise ValueError(f"默认模型 {self.default_llm} 不在配置中")
        
        # 从配置加载重试参数
        self.retry_config = RETRY_CONFIG["llm"]

    def _prepare_request_parameters(self, llm_name: str) -> tuple:
        """准备 LLM API 请求的 URL 和 headers"""
        config = self.llm_configs[llm_name]

        url_params = config["url_params"]
        if url_params:
            formatted_params = {k: v.format(key=config["key"]) for k, v in url_params.items()}
            query_string = "&".join([f"{k}={v}" for k, v in formatted_params.items()])
            request_url = f"{config['url']}?{query_string}"
        else:
            request_url = config["url"]

        headers = {k: v.format(key=config["key"]) for k, v in config["headers"].items()}

        return request_url, headers

    def _create_payload(self, llm_name: str, messages: List[Dict[str, str]],
                        temperature: float = 0, n: int = 1, **kwargs) -> Dict:
        """创建 LLM API 请求的 payload"""
        return {
            "model": self.llm_configs[llm_name]["model"],
            "messages": messages,
            "temperature": temperature,
            "n": n,
            **kwargs
        }

    def chat_completion(self, messages: List[Dict[str, str]], llm_name: str = None,
                        temperature: float = 0, n: int = 1, max_retries: int = None,
                        initial_delay: float = None, **kwargs) -> Dict:
        """调用 LLM 的聊天接口，带自动重试功能"""
        llm_name = llm_name or self.default_llm
        if llm_name not in self.llm_configs:
            raise ValueError(f"未知的 LLM 模型: {llm_name}")

        # 使用配置的重试参数
        max_retries = max_retries if max_retries is not None else self.retry_config["max_retries"]
        initial_delay = initial_delay if initial_delay is not None else self.retry_config["initial_delay"]
        backoff_factor = self.retry_config["backoff_factor"]
        jitter_max = self.retry_config["jitter_max"]

        payload = self._create_payload(llm_name, messages, temperature, n, **kwargs)
        request_url, headers = self._prepare_request_parameters(llm_name)

        # 优先使用模型自身配置的 timeout
        timeout = self.llm_configs[llm_name].get("timeout") or self.retry_config["timeout"]

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(request_url, json=payload, headers=headers, timeout=timeout, verify=False)

                if response.status_code == 200:
                    return response.json()

                if attempt < max_retries:
                    delay = initial_delay * (backoff_factor ** attempt) + random.uniform(0, jitter_max)
                    logger.warning(f"LLM请求失败（第 {attempt+1}/{max_retries} 次），状态码: {response.status_code}，{delay:.1f}s 后重试")
                    time.sleep(delay)
                else:
                    logger.error(f"LLM最终失败（已重试 {max_retries} 次），状态码: {response.status_code}")
                    return {"error": f"API请求失败，状态码: {response.status_code}", "details": response.text}

            except Exception as e:
                if attempt < max_retries:
                    delay = initial_delay * (backoff_factor ** attempt) + random.uniform(0, jitter_max)
                    logger.warning(f"LLM请求异常（第 {attempt+1}/{max_retries} 次）: {e}，{delay:.1f}s 后重试")
                    time.sleep(delay)
                else:
                    logger.error(f"LLM最终失败（已重试 {max_retries} 次）: {e}")
                    return {"error": "调用LLM时发生错误", "details": str(e)}

        return {"error": "达到最大重试次数"}
