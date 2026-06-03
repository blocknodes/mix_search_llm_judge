"""
LLM 相关性评分模块
"""
import json
import logging
from typing import Dict, List

from llm_client import LLMClient
from config import JUDGE_CONFIG, RETRY_CONFIG

logger = logging.getLogger(__name__)


def build_relevance_prompt(query: str, filename: str, block: str) -> str:
    """构建相关性评分的 prompt"""
    return f"""
你是一名专业的信息检索与问答评估专家。请根据用户提出的问题（query）和检索到的文本块（block）及其所在文件名（filename），从多维度严格判断该文本块与问题的相关性，并进行细粒度评分。请仅依据文本块本身内容进行判断，不考虑外部信息或来源。

请综合考虑以下方面：
1. 主体一致性：文本块内容结合文件名是否与问题的主语和核心主体高度一致。只有当内容紧密围绕问题主体展开，才可视为相关。
2. 事实/数据支持：文本块内容结合文件名是否为问题提供了直接或间接的事实、数据、证据或操作方法。仅当这些信息与问题主体高度相关时，才算有效支持。
3. 解释说明：文本块内容结合文件名是否对问题涉及的概念、原理、流程等进行了有效解释或补充说明。泛泛而谈或与问题主体无关的内容不计入相关性。
4. 语义相关性：文本块内容结合文件名与问题在语义上是否高度一致。仅有部分词汇相关但语义不一致的，相关性应为低分或零分。
5. 权威性与数据源：如文本块内容明确来自权威或与问题相关的数据来源，可适当提高相关性评分，但前提是内容与问题主体高度相关。
6. 对于问题中涉及具体产品的参数（如BCD-515P60FZMAD的产品尺寸是多少？等），文本块内容结合文件名是否准确匹配或高度相关。仅有部分匹配但不准确的，相关性应为低分或零分。

评分原则：相关性是指文本块内容结合文件名与用户问题的主体高度相关，仅以文本块结合文件名的本身内容为依据，不考虑文本块的来源或其他外部信息。例如，若问题为"海信空调"，而文本块内容为"海信抽油烟机"的说明，尽管两者都来自海信，但内容未涉及问题主体，因此相关性得分应很低。

评分细则：
- 10分：文本块内容能够完整、准确地回答用户问题，涵盖所有关键信息，与问题主语和主体高度相关，无遗漏或错误。
- 1-9分：文本块内容与问题主体有部分相关，能够部分回答问题，但信息不全或有细节缺失。分数越高，表示相关性越强，内容越接近完整答案。
- 0分：文本块内容与问题主体完全无关，无法提供任何有效信息，或仅与问题的部分词汇相关但未涉及问题主语和主体。

判定依据
- 仅当文本块内容紧密围绕问题主体展开，并能直接或间接回答问题时，才可视为相关。
- 仅有部分词汇或片段相关，但整体内容未涉及问题主体时，不应视为相关。
- 排除泛泛描述、主观评价、无事实或操作支持的内容。

输入：
用户问题（query）：{query}
文本块所在文件名（filename）：{filename}
检索文本块（block）：{block}

请将你的相关性评分以如下严格的 JSON 格式输出，无需其他说明，示例：
{{"score": 8}}
"""


def judge_relevance(query: str, candidates: List[Dict], llm_client: LLMClient = None,
                    top_n: int = None) -> List[Dict]:
    """
    对检索结果进行 LLM 相关性评分
    
    Args:
        query: 用户查询
        candidates: 检索结果列表
        llm_client: LLM 客户端实例
        top_n: 评分的结果数量
    
    Returns:
        带有 llm_relevance 评分的候选结果列表
    """
    if llm_client is None:
        llm_client = LLMClient()
    
    top_n = top_n or JUDGE_CONFIG["top_n"]
    
    for item in candidates[:top_n]:
        filename = item.get('filename', '')
        block = item.get('block_content') or f"{item.get('title', '')}\n{item.get('content', '')}"
        
        prompt = build_relevance_prompt(query, filename, block)
        messages = [{"role": "user", "content": prompt}]
        
        response = llm_client.chat_completion(
            messages=messages,
            temperature=JUDGE_CONFIG["temperature"]
            # max_retries 使用 RETRY_CONFIG 中的配置
        )
        
        try:
            score = json.loads(response['choices'][0]['message']['content'])['score']
            item['llm_relevance'] = score
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning(f"解析LLM响应失败: {e}, response={response}")
            item['llm_relevance'] = -1
    
    return candidates


def compute_hit_metrics(candidates: List[Dict], threshold: int = None, hit_ns: List[int] = None) -> Dict:
    """
    计算 hit@n 指标（n 值可配置）
    
    Args:
        candidates: 带有 llm_relevance 评分的候选结果
        threshold: 相关性阈值
        hit_ns: 要计算的 N 值列表
    
    Returns:
        包含各 hit@n 的字典
    """
    threshold = threshold or JUDGE_CONFIG["hit_threshold"]
    hit_ns = hit_ns or JUDGE_CONFIG["hit_ns"]
    
    result = {f"hit{n}": False for n in hit_ns}
    
    # 找到第一个命中的位置
    hit_pos = -1
    for i, item in enumerate(candidates):
        if item.get('llm_relevance', 0) >= threshold:
            hit_pos = i
            break
    
    if hit_pos >= 0:
        for n in hit_ns:
            if hit_pos < n:
                result[f"hit{n}"] = True
    
    return result
