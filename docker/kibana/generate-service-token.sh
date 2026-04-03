#!/bin/bash
set -euo pipefail

es_url="${ELASTICSEARCH_URL:-http://elasticsearch:9200}"
token_dir="${TOKEN_DIR:-/run/kibana-token}"
token_file="${TOKEN_FILE:-${token_dir}/service_account_token}"
token_name_prefix="${TOKEN_NAME_PREFIX:-kibana-docker}"
auth_user="${ELASTIC_USERNAME:-elastic}"
auth_password="${ELASTIC_PASSWORD:?ELASTIC_PASSWORD is required}"

mkdir -p "${token_dir}"

echo "Waiting for Elasticsearch at ${es_url}..."
until curl -fsS -u "${auth_user}:${auth_password}" "${es_url}" >/dev/null; do
  sleep 2
done

if [ -s "${token_file}" ]; then
  existing_token="$(tr -d '\r\n' < "${token_file}")"
  if [ -n "${existing_token}" ] && curl -fsS -H "Authorization: Bearer ${existing_token}" "${es_url}/_security/_authenticate" | grep -Eq '"username"[[:space:]]*:[[:space:]]*"elastic/kibana"'; then
    echo "Reusing existing Kibana service account token from ${token_file}"
    exit 0
  fi
fi

token_name="${token_name_prefix}-$(date +%s)"
response="$(curl -fsS -u "${auth_user}:${auth_password}" -H 'Content-Type: application/json' -X POST "${es_url}/_security/service/elastic/kibana/credential/token/${token_name}")"
token_value="$(printf '%s' "${response}" | tr -d '\n' | sed -n 's/.*"value"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

if [ -z "${token_value}" ]; then
  echo "Failed to extract Kibana service account token from Elasticsearch response" >&2
  echo "${response}" >&2
  exit 1
fi

printf '%s' "${token_value}" > "${token_file}"
chmod 644 "${token_file}"
echo "Stored Kibana service account token in ${token_file}"
