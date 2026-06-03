#!/bin/bash
# 批量两阶段示例：批量检索 -> 批量评分
# 用法: bash example_batch_two_stage.sh queries.txt
#
# queries.txt 格式（每行一个 query）:
#   冰箱保鲜室有多大
#   空调怎么开启自清洁
#   洗衣机故障代码F23

SERVER="http://10.19.96.219:4063"
INPUT_FILE="${1:-queries.txt}"
RETRIEVE_RESULTS="retrieve_results"
BATCH_JUDGE_REQUEST="judge_batch_request.json"
FINAL_RESULT="judge_batch_result.json"

# KBP 参数（按需修改）
BASE_URL="https://inner-apisix.hisense.com"
RETRIEVAL_PATH="/kbp/openapi/kbp/mix/retrieval"
USER_KEY="gzsomsltqzgc3crdmatlgucpghc9erjk"
API_KEY="a4c77895-cbdf-4017-b4ab-58bb2c129bfd"

mkdir -p ${RETRIEVE_RESULTS}

echo "=== 第一阶段：批量检索 ==="
echo "输入文件: ${INPUT_FILE}"

idx=0
while IFS= read -r query; do
  # 跳过空行
  [ -z "$query" ] && continue
  idx=$((idx + 1))

  echo -n "  [${idx}] 检索: ${query:0:40}... "

  # 构造请求并调用 /retrieve
  curl -s -X POST ${SERVER}/retrieve \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": \"${query}\",
      \"base_url\": \"${BASE_URL}\",
      \"retrieval_path\": \"${RETRIEVAL_PATH}\",
      \"user_key\": \"${USER_KEY}\",
      \"api_key\": \"${API_KEY}\",
      \"top_k\": 10,
      \"search_mode\": \"hybrid\",
      \"search_strategy\": \"precise\"
    }" \
    -o "${RETRIEVE_RESULTS}/${idx}.json"

  echo "OK"
done < "${INPUT_FILE}"

echo ""
echo "共检索 ${idx} 条，结果保存在 ${RETRIEVE_RESULTS}/"
echo ""

echo "=== 组装批量评分请求 ==="

# 把所有检索结果组装成 judge/batch 的输入格式
echo -n '{"items": [' > ${BATCH_JUDGE_REQUEST}
first=true
for f in $(ls ${RETRIEVE_RESULTS}/*.json | sort -V); do
  # 跳过检索失败的（包含 error 字段的）
  if grep -q '"error"' "$f" 2>/dev/null; then
    echo "  跳过失败: $f"
    continue
  fi
  if [ "$first" = true ]; then
    first=false
  else
    echo -n ',' >> ${BATCH_JUDGE_REQUEST}
  fi
  cat "$f" >> ${BATCH_JUDGE_REQUEST}
done
echo ']}' >> ${BATCH_JUDGE_REQUEST}

echo "请求文件: ${BATCH_JUDGE_REQUEST}"
echo ""

echo "=== 第二阶段：批量 LLM 评分 ==="
curl -s -X POST ${SERVER}/judge/batch \
  -H "Content-Type: application/json" \
  -d @${BATCH_JUDGE_REQUEST} \
  -o ${FINAL_RESULT}

echo "评分完成！结果: ${FINAL_RESULT}"
echo ""

echo "=== Stats ==="
python3 -c "
import json
with open('${FINAL_RESULT}') as f:
    data = json.load(f)
stats = data.get('stats', {})
for k, v in stats.items():
    print(f'  {k}: {v}')
"
