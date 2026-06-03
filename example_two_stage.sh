#!/bin/bash
# 两阶段完整示例：检索 -> 评分
# 用法: bash example_two_stage.sh

SERVER="http://10.19.96.219:4063"

echo "=== 第一阶段：检索 ==="
curl -s -X POST ${SERVER}/retrieve \
  -H "Content-Type: application/json" \
  -d @retrieve_request.json \
  -o retrieve_result.json

echo "检索结果已保存到 retrieve_result.json"
echo ""

echo "=== 第二阶段：LLM 评分 ==="
curl -s -X POST ${SERVER}/judge \
  -H "Content-Type: application/json" \
  -d @retrieve_result.json \
  -o judge_result.json

echo "评分结果已保存到 judge_result.json"
echo ""

echo "=== 结果 ==="
cat judge_result.json | python -m json.tool
