# Telegram Bot с Yandex Agent

Простой Telegram бот, который работает с Yandex Agent через Responses API с поддержкой памяти.

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Настройте `.env` файл:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
YANDEX_API_KEY_SECRET=your_api_key
YANDEX_FOLDER_ID=your_folder_id
YANDEX_SERVICE_ACCOUNT_ID=your_service_account_id
YC_AGENT_ID=your_agent_id
YDB_ENDPOINT=your_ydb_endpoint
YDB_DATABASE=your_ydb_database
RESPONSES_BASE_URL=https://rest-assistant.api.cloud.yandex.net/v1
```

3. Поместите файл `key.json` с ключом сервисного аккаунта в корень проекта.

## Запуск

```bash
python bot.py
```

## Команды

- `/start` - начать работу с ботом
- `/new` - сбросить контекст диалога

## Особенности

- ✅ Работа с Yandex Agent через Responses API
- ✅ Поддержка инструментов (MCP)
- ✅ Память диалога через previous_response_id
- ✅ Хранение состояния в YDB
- ✅ Автоматическая аутентификация через сервисный аккаунт