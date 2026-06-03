# 混合检索 + LLM 相关性评分 Pipeline

自动化检索质量评估工具。通过 KBP 混合检索获取候选文档，再利用 LLM-as-a-Judge 对检索结果进行相关性评分，最终计算 Hit@N 指标来衡量检索系统效果。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        评估 Pipeline                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │ Benchmark│───▶│ 混合检索 │───▶│ LLM 评分 │───▶│ 指标计算 │ │
│   │  数据集  │    │  (KBP)   │    │  (Judge) │    │  Hit@N   │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│        │               │               │               │        │
│        ▼               ▼               ▼               ▼        │
│   Query + Cat     Top-K 候选     相关性分数      Hit@1/3/10    │
│                                   (0-10)                        │
└─────────────────────────────────────────────────────────────────┘
```

## 目录结构

```
mix_search_llm_judge/
├── config.py                  # 集中配置（API密钥、检索参数、LLM配置、重试策略等）
├── kbp_client.py              # KBP 混合检索客户端（向量+关键词融合检索）
├── llm_client.py              # LLM 客户端（支持多模型后端，自动重试）
├── llm_judge.py               # LLM 相关性评分模块（Prompt + 评分解析）
├── pipeline.py                # 核心处理流程（两阶段 Pipeline + 多线程批量处理）
├── run.py                     # CLI 一键执行入口
├── server.py                  # FastAPI HTTP 服务（提供 REST API）
├── stats.py                   # 结果统计工具（从 result.jsonl 计算 Hit@N）
├── sample_benchmark.py        # Benchmark 采样工具（按类别比例采样）
├── benchmark.csv              # 完整评测集
├── benchmark_sampled.csv      # 采样后的评测集
├── queries.txt                # 示例查询文件
├── retrieve_request.json      # 检索请求示例
├── example_two_stage.sh       # 两阶段 curl 示例（单条）
├── example_batch_two_stage.sh # 两阶段 curl 示例（批量）
├── result.jsonl               # 评测结果输出
└── README.md
```

## 环境依赖

```bash
pip install requests fastapi uvicorn pydantic
```

## 快速开始

### 1. 单条查询测试

```bash
# 默认跑 benchmark.csv
python run.py

# 指定单条查询
python run.py --query "冰箱保鲜室有多大" --category product

# 指定检索数量和评分数量
python run.py --query "空调怎么开启自清洁功能" --top-k 10 --judge-top-n 5
```

### 2. 批量 Benchmark 评测

```bash
# 使用默认 benchmark.csv，结果输出到 result.jsonl
python run.py

# 指定 benchmark 文件和输出路径
python run.py --benchmark benchmark_sampled.csv --output result_sampled.jsonl

# 指定并发线程数（默认5）
python run.py --workers 10
```

### 3. 启动 HTTP 服务

```bash
# 默认端口 8080
python server.py

# 指定端口
python server.py --port 4063

# 使用 uvicorn 启动（支持多 worker）
uvicorn server:app --host 0.0.0.0 --port 8080 --workers 4
```

服务启动后访问 `http://localhost:8080/docs` 查看交互式 API 文档。

### 4. 统计结果

```bash
# 默认统计 hit@1, hit@3, hit@10
python stats.py

# 自定义统计指标
python stats.py --hit 1 3 5 10

# 指定输入文件和阈值
python stats.py --input result_1k.jsonl --threshold 7
```

### 5. Benchmark 采样

```bash
# hr 类别采样 10%，product 保留全部
python sample_benchmark.py --ratio hr=0.1

# 多类别采样
python sample_benchmark.py --ratio hr=0.1 product=0.5

# 按条数采样
python sample_benchmark.py --ratio hr=20 product=100

# 指定输入输出
python sample_benchmark.py --input benchmark.csv --output benchmark_sampled.csv --ratio hr=0.1
```

## HTTP API 接口

### 健康检查

```
GET /health
```

### 单条查询（检索 + 评分）

```
POST /query
```

```json
{
  "query": "冰箱保鲜室有多大",
  "category": "product",
  "top_k": 10,
  "judge_top_n": 3
}
```

### 第一阶段：仅检索

```
POST /retrieve
```

```json
{
  "query": "空调怎么开启自清洁功能",
  "category": "product",
  "top_k": 10,
  "search_mode": "hybrid",
  "search_strategy": "precise"
}
```

### 第二阶段：仅 LLM 评分

```
POST /judge
```

输入为 `/retrieve` 的输出：

```json
{
  "query": "空调怎么开启自清洁功能",
  "category": "product",
  "candidates": [
    {
      "filename": "空调使用说明.pdf",
      "title": "自清洁功能",
      "content": "按下遥控器上的清洁按键...",
      "score": 0.92
    }
  ],
  "judge_top_n": 3
}
```

### 批量评分

```
POST /judge/batch
```

```json
{
  "items": [
    {"query": "问题1", "category": "product", "candidates": [...]},
    {"query": "问题2", "category": "product", "candidates": [...]}
  ],
  "judge_top_n": 3
}
```

### 批量查询

```
POST /batch
```

```json
{
  "queries": [
    {"query": "冰箱保鲜室有多大", "category": "product"},
    {"query": "空调怎么开启自清洁功能", "category": "product"}
  ],
  "top_k": 10,
  "judge_top_n": 3
}
```

## 两阶段 Shell 示例

适用于需要分步调试或与外部系统集成的场景。

### 单条两阶段

```bash
bash example_two_stage.sh
```

### 批量两阶段

```bash
# 从 queries.txt 读取查询，逐条检索后批量评分
bash example_batch_two_stage.sh queries.txt
```

## CLI 参数说明

### run.py

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--query` | `-q` | 单条查询文本 | - |
| `--category` | `-c` | 查询类别 (`product` / `hr`) | `product` |
| `--benchmark` | `-b` | Benchmark CSV 文件路径 | `benchmark.csv` |
| `--output` | `-o` | 输出文件路径 | `result.jsonl` |
| `--top-k` | - | 检索返回数量 | 使用 config 配置 |
| `--judge-top-n` | - | LLM 评分的候选数量 | `3` |
| `--workers` | `-w` | 并发线程数 | `5` |

### stats.py

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--input` | `-i` | 输入 result.jsonl 文件 | `result.jsonl` |
| `--hit` | `-n` | 要统计的 Hit@N 值列表 | `1 3 10` |
| `--threshold` | `-t` | 相关性得分阈值 | `8` |

### sample_benchmark.py

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--input` | `-i` | 输入 CSV 文件 | `benchmark.csv` |
| `--output` | `-o` | 输出 CSV 文件 | `benchmark_sampled.csv` |
| `--ratio` | `-r` | 采样比例 (`cat=ratio`，≤1为比例，>1为条数) | `hr=0.1` |
| `--seed` | - | 随机种子 | `42` |

## 配置说明

所有配置集中在 `config.py`，主要包含以下部分：

### KBP 检索配置

```python
KBP_BASE_URL = "https://inner-apisix-test.hisense.com"
KBP_USER_KEY = "..."
KBP_API_KEY = "..."
```

### LLM 模型配置

支持多个 LLM 后端，通过 `DEFAULT_LLM` 切换：

| 模型名 | 说明 |
|--------|------|
| `deepseek` | DeepSeek-V3 |
| `qwen35` | Qwen3.5-397B |
| `gpt54` | GPT-4.1 (默认) |

新增模型只需在 `LLM_CONFIGS` 字典中添加配置即可。

### 检索参数

```python
RETRIEVAL_CONFIG = {
    "top_k": 10,              # 返回候选数
    "score_threshold": 0,     # 分数阈值
    "search_mode": "hybrid",  # 检索模式: hybrid / vector / keyword
    "search_strategy": "precise",  # 搜索策略: precise / fast
}
```

### LLM Judge 配置

```python
JUDGE_CONFIG = {
    "top_n": 10,           # 对前N个结果评分
    "hit_threshold": 8,    # 相关性阈值（≥8分视为相关）
    "hit_ns": [1, 3, 10], # 计算哪些 Hit@N
    "temperature": 0       # LLM 温度
}
```

### 并发与重试配置

```python
CONCURRENCY_CONFIG = {
    "max_workers": 5,   # 最大并发线程数
    "batch_size": 10    # 批处理大小
}

RETRY_CONFIG = {
    "kbp": {"max_retries": 10, "initial_delay": 0.5, "backoff_factor": 2.0, "jitter_ratio": 0.5},
    "llm": {"max_retries": 20, "initial_delay": 1.0, "backoff_factor": 2.0, "jitter_max": 0.5, "timeout": 30}
}
```

## 输出格式

### result.jsonl（每行一条 JSON）

```json
{
  "query": "冰箱保鲜室有多大",
  "category": "product",
  "candidates": [
    {
      "kind": "document",
      "filename": "BCD-515P60FZMAD说明书.pdf",
      "title": "产品参数",
      "content": "冷藏室容积：345L，保鲜室容积：...",
      "category_path": "冰箱/对开门",
      "score": 0.92,
      "llm_relevance": 9
    }
  ],
  "hit1": true,
  "hit3": true,
  "hit10": true
}
```

### 统计输出示例

```
文件: result.jsonl
总条数: 654
相关性阈值: >= 8

============================================================
指标           命中数      比率
------------------------------------------------------------
Hit@1        512        78.29%
Hit@3        589        90.06%
Hit@10       621        94.95%

============================================================
按类别统计:

  [product] (共 600 条)
    Hit@1    480 / 600  = 80.00%
    Hit@3    550 / 600  = 91.67%
    Hit@10   580 / 600  = 96.67%

  [hr] (共 54 条)
    Hit@1     32 /  54  = 59.26%
    Hit@3     39 /  54  = 72.22%
    Hit@10    41 /  54  = 75.93%
```

## LLM 评分标准

评分维度（0-10分）：

| 维度 | 说明 |
|------|------|
| 主体一致性 | 文本块内容是否与问题的核心主体高度一致 |
| 事实/数据支持 | 是否提供了直接或间接的事实、数据、操作方法 |
| 语义相关性 | 内容与问题在语义上是否高度一致 |
| 产品参数匹配 | 涉及具体产品参数时是否准确匹配 |

评分细则：
- **10分**：完整、准确回答问题，涵盖所有关键信息
- **1-9分**：部分相关，分数越高相关性越强
- **0分**：与问题主体完全无关

Hit@N 判定：前 N 个候选中存在 `llm_relevance >= 8` 的结果即为命中。

## 设计特点

- **两阶段解耦**：检索和评分可独立运行，便于调试和集成
- **多线程并发**：IO 密集型任务使用线程池加速，每线程独立客户端实例
- **指数退避重试**：KBP 和 LLM 调用均带退避 + 随机抖动，避免瞬时故障
- **多 LLM 后端**：配置文件添加即可切换模型
- **实时进度条**：批量处理时显示进度、ETA、实时 Hit 统计
- **HTTP 服务模式**：FastAPI 提供 REST API，支持与外部系统集成
- **配置集中化**：所有参数统一管理，便于环境切换

## Benchmark 数据格式

`benchmark.csv` 格式：

```csv
query,cat
冰箱保鲜室有多大,product
HR的典型价值流分别支撑什么,hr
```

| 字段 | 说明 |
|------|------|
| `query` | 用户查询文本 |
| `cat` | 查询类别（`product` = 产品类，`hr` = 人力资源类） |
