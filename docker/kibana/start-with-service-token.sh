#!/bin/sh
set -eu

token_file="${TOKEN_FILE:-/run/kibana-token/service_account_token}"
wait_seconds="${TOKEN_WAIT_SECONDS:-60}"

while [ ! -s "${token_file}" ]; do
  wait_seconds=$((wait_seconds - 1))
  if [ "${wait_seconds}" -le 0 ]; then
    echo "Kibana service account token file not found: ${token_file}" >&2
    exit 1
  fi

  sleep 1
done

export ELASTICSEARCH_SERVICEACCOUNTTOKEN="$(tr -d '\r\n' < "${token_file}")"
exec /bin/tini -- /usr/local/bin/kibana-docker
