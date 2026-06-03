"""
配置文件 - 集中管理所有配置项
"""

# KBP 检索 API 配置
KBP_BASE_URL = "https://inner-apisix-test.hisense.com"
KBP_USER_KEY = "qimfvt7lwtqeyangfl259vjg8fzdhh5l"
KBP_RETRIEVAL_PATH = "/kbp-test/openapi/kbp/mix/retrieval"
KBP_API_KEY = "83dd8d9d-6a77-4954-9071-aa195fb6b406"

# LLM 配置
LLM_CONFIGS = {
    "deepseek": {
        "url": "https://inner-apisix.hisense.com/compatible-openai/v1/chat/completions",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer {key}"},
        "key": "Oi4rzFyLbMOmqVn8YYEyT2Pt0mkr3lgU",
        "model": "deepseek-v3-jhk",
        "url_params": {"user_key": "nregzh6g2oviajyjstgzlhjsjmp9rtql"},
        "timeout": 180
    },
    "qwen35": {
        "url": "https://inner-apisix.hisense.com/compatible-openai/v1/chat/completions",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer {key}"},
        "key": "Oi4rzFyLbMOmqVn8YYEyT2Pt0mkr3lgU",
        "model": "qwen3-5-397b",
        "url_params": {"user_key": "nregzh6g2oviajyjstgzlhjsjmp9rtql"},
        "timeout": 180
    },
    "gpt55": {
        "url": "http://aibi-superset.hisense.com:4046/v1/chat/completions",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer {key}"},
        "key": "sk-PTkpbJEUEgS3yCHJedSxEQ",
        "model": "gpt-5.5",
        "url_params": {},
        "timeout": 180
    },
    "qwen3_35b": {
        "url": "http://aibi-superset.hisense.com:4046/v1/chat/completions",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer {key}"},
        "key": "sk-i54TP7rpcV_NoDoD-S6N6Q",
        "model": "qwen3-6-35b",
        "url_params": {},
        "timeout": 180
    },
    "qwen3_397b": {
        "url": "http://aibi-superset.hisense.com:4046/v1/chat/completions",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer {key}"},
        "key": "sk-uhJc7qbF2eTZu3TPTz7MIA",
        "model": "hx-qwen3.5-397b",
        "url_params": {},
        "timeout": 180
    }
}

# 默认使用的 LLM
DEFAULT_LLM = "gpt54"

# 检索配置
RETRIEVAL_CONFIG = {
    "top_k": 10,
    "score_threshold": 0,
    "search_mode": "hybrid",
    "search_strategy": "precise",  # 搜索策略: precise / fast
    "tracing_model": False
}

# LLM Judge 配置
JUDGE_CONFIG = {
    "top_n": 10,  # 对前N个结果进行LLM评分
    "hit_threshold": 8,  # 相关性得分阈值
    "hit_ns": [1, 3, 6, 10],  # 计算哪些 Hit@N 指标
    "temperature": 0
}

# 并发配置
CONCURRENCY_CONFIG = {
    "max_workers": 5,  # 最大并发线程数
    "batch_size": 10   # 批处理大小
}

# 重试配置
RETRY_CONFIG = {
    # KBP 检索重试
    "kbp": {
        "max_retries": 10,
        "initial_delay": 0.5,
        "backoff_factor": 2.0,
        "jitter_ratio": 0.5  # 随机抖动比例
    },
    # LLM 调用重试
    "llm": {
        "max_retries": 20,
        "initial_delay": 1.0,
        "backoff_factor": 2.0,
        "jitter_max": 0.5,  # 最大随机抖动秒数
        "timeout": 30       # 请求超时秒数
    }
}
