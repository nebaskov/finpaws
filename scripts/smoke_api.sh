#!/usr/bin/env sh
set -eu

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="${EMAIL:-smoke-$(date +%s)-$$@finpaws.dev}"
PASSWORD="${PASSWORD:-superpassword123}"

echo "Running API smoke test against ${BASE_URL}"

health_payload="$(curl -fsS "${BASE_URL}/health")"
python3 -c 'import json,sys; data=json.loads(sys.argv[1]); assert data.get("status") == "ok"' "$health_payload"

register_payload="$(curl -fsS -X POST "${BASE_URL}/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\",\"display_name\":\"smoke\"}")"
TOKEN="$(python3 -c 'import json,sys;print(json.loads(sys.argv[1])["access_token"])' "$register_payload")"
AUTH="Authorization: Bearer ${TOKEN}"

curl -fsS "${BASE_URL}/me" -H "${AUTH}" >/dev/null

curl -fsS -X POST "${BASE_URL}/transactions/income" \
  -H "${AUTH}" -H "Content-Type: application/json" \
  -d '{"amount":"10000","description":"salary","currency":"RUB"}' >/dev/null

curl -fsS -X POST "${BASE_URL}/transactions/expense" \
  -H "${AUTH}" -H "Content-Type: application/json" \
  -d '{"amount":"500","description":"Yandex Taxi","currency":"RUB"}' >/dev/null

report_payload="$(curl -fsS "${BASE_URL}/report?days=30" -H "${AUTH}")"
python3 -c 'import json,sys; data=json.loads(sys.argv[1]); assert data["user_id"]; assert "income" in data and "spent" in data and "balance" in data' "$report_payload"

echo "Smoke test passed"
