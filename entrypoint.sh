#!/bin/sh
set -e

# Если секрет сервисного аккаунта передан как переменная, создадим key.json в рантайме
if [ -n "$YC_SA_KEY_JSON" ]; then
  echo "$YC_SA_KEY_JSON" > /app/key.json
  export YANDEX_SERVICE_ACCOUNT_KEY_FILE=/app/key.json
  export YC_SERVICE_ACCOUNT_KEY_FILE=/app/key.json
fi

exec python /app/bot.py


