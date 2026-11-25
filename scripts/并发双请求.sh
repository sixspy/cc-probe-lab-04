#!/usr/bin/env bash
# 争用收工脚本：同号两路坏点并发双请求，断言只成一匣、另一路幂等驳回。
# 用法：
#   ./scripts/并发双请求.sh                  # 默认打 http://127.0.0.1:8130
#   BASE_URL=http://127.0.0.1:8100 ./scripts/并发双请求.sh
# 前置：服务已起（docker compose up -d --build）。登录页为静态表单，接口无鉴权。
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8130}"
MSG_ID="K-race-$(date +%s)"
PAYLOAD=$(cat <<JSON
{"批次编号":"并发双请求","报文":[{"报文编号":"${MSG_ID}","站点键":"站-河东","指标键":"PM25","读数":120.0,"观测时":"2026-11-24T09:10:00Z"}]}
JSON
)

echo "基址=${BASE_URL} 同号=${MSG_ID}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

# 两路并发 POST，同一报文号、同一读数。
curl -sS -X POST "${BASE_URL}/api/观测报文/装载" -H 'Content-Type: application/json' \
  -d "${PAYLOAD}" -o "${TMP_DIR}/r1.json" &
curl -sS -X POST "${BASE_URL}/api/观测报文/装载" -H 'Content-Type: application/json' \
  -d "${PAYLOAD}" -o "${TMP_DIR}/r2.json" &
wait

echo "--- 响应1"; jq -c '{in:.["入流"],lan:.["入栏"],bad:.["坏点"],rej:.["驳回"],detail:.["明细"]}' "${TMP_DIR}/r1.json"
echo "--- 响应2"; jq -c '{in:.["入流"],lan:.["入栏"],bad:.["坏点"],rej:.["驳回"],detail:.["明细"]}' "${TMP_DIR}/r2.json"

BAD_SUM=$(jq -s 'map(.["坏点"] // 0) | add' "${TMP_DIR}/r1.json" "${TMP_DIR}/r2.json")
REJ_SUM=$(jq -s 'map(.["驳回"] // 0) | add' "${TMP_DIR}/r1.json" "${TMP_DIR}/r2.json")
echo "汇总：坏点=${BAD_SUM}（须=1） 驳回=${REJ_SUM}（须=1）"

PEN_ROWS=$(curl -sS "${BASE_URL}/api/坏点匣" | jq --arg n "${MSG_ID}" '[.[] | select(.["报文编号"]==$n)] | length')
OBS_ROWS=$(curl -sS "${BASE_URL}/api/观测报文" | jq --arg n "${MSG_ID}" '[.[] | select(.["报文编号"]==$n)] | length')
VOUCHER=$(curl -sS "${BASE_URL}/api/坏点旁路保留" | jq -c --arg n "${MSG_ID}" '[.[] | select(.["报文编号"]==$n)]')
echo "匣行=${PEN_ROWS}（须=1） 观测流=${OBS_ROWS}（须=1）"
echo "旁路保留回读：${VOUCHER}"

fail=0
[ "${BAD_SUM}" = "1" ] || { echo "红：坏点成功数=${BAD_SUM}，应恰为 1"; fail=1; }
[ "${REJ_SUM}" = "1" ] || { echo "红：幂等驳回数=${REJ_SUM}，应恰为 1"; fail=1; }
[ "${PEN_ROWS}" = "1" ] || { echo "红：坏点匣双行=${PEN_ROWS}，互斥失效"; fail=1; }
[ "${OBS_ROWS}" = "1" ] || { echo "红：观测流行数=${OBS_ROWS}，应恰为 1"; fail=1; }
echo "${VOUCHER}" | jq -e '.[0]["原观测可回读"] == true and .[0]["同票一致"] == true' >/dev/null \
  || { echo "红：旁路凭证回读不到原观测或同票不一致"; fail=1; }

if [ "${fail}" -eq 0 ]; then
  echo "绿：同号并发只成一匣一观测，原观测凭证可回读。"
else
  echo "争用失败，退出码 1。"
  exit 1
fi
