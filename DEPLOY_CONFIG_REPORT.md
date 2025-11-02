# 📋 ПОЛНЫЙ ОТЧЕТ О КОНФИГУРАЦИИ ДЕПЛОЯ
## Beauty Salon AI Assistant → Yandex Cloud Serverless Container

**Дата составления:** 2025-01-20  
**Проект:** beauty_salon_ai  
**Целевая платформа:** Yandex Cloud Serverless Container

---

## 1. 🐳 DOCKERFILE

**Расположение:** `Dockerfile`  
**Архитектура:** Multi-stage build (builder + runtime)

```dockerfile
# --- Этап 1: Сборка зависимостей ---
# Используем официальный образ Python как базовый для сборки
FROM python:3.10-slim as builder

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости для сборки пакетов
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN pip install poetry

# Копируем файлы управления зависимостями
COPY poetry.lock pyproject.toml ./

# Устанавливаем зависимости проекта, исключая dev-зависимости,
# и создаем виртуальное окружение внутри /app/.venv
RUN poetry config virtualenvs.create false && \
    poetry install --only=main --no-root --no-interaction --no-ansi --sync && \
    python -c "import ydb; print('YDB successfully installed')"


# --- Этап 2: Создание финального образа ---
# Используем тот же базовый образ для уменьшения размера
FROM python:3.10-slim

# Устанавливаем системные зависимости для runtime
RUN apt-get update && apt-get install -y \
    libpq5 \
    libffi8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем установленные зависимости из этапа сборки
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Копируем исходный код приложения
COPY app ./app
COPY dialogue_patterns.json .
COPY scripts ./scripts

# Команда для запуска приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Ключевые особенности:
- **Базовый образ:** `python:3.10-slim`
- **Multi-stage build:** Оптимизация размера образа
- **Менеджер зависимостей:** Poetry
- **Команда запуска:** `uvicorn app.main:app --host 0.0.0.0 --port 8080`
- **EXPOSE:** Не указан явно (порт 8080 используется по умолчанию в Serverless Container)
- **ENTRYPOINT:** Не указан, используется CMD

---

## 2. 📄 ФАЙЛ ЗАПУСКА (main.py)

**Расположение:** `app/main.py`  
**Тип приложения:** FastAPI ASGI приложение

```python
from fastapi import FastAPI, Request, BackgroundTasks
import logging
import os
from dotenv import load_dotenv
from app.core.logging_config import setup_logging
from app.core.config import settings
from app.api import telegram
from app.services.dialogue_tracer_service import clear_debug_logs
from app.schemas.telegram import Update
from app.api.telegram import process_telegram_update
from app.core.database import init_database

# Загружаем переменные окружения и настраиваем логирование сразу при импорте модуля,
# чтобы одинаково работало локально и в облаке (Serverless/Container)
load_dotenv(os.getenv("ENV_FILE", ".env"))
setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Beauty Salon AI Assistant",
    version="0.1.0"
)

app.include_router(telegram.router, prefix="/telegram", tags=["Telegram"])


@app.on_event("startup")
async def startup_event():
    """Выполняется при запуске приложения."""
    logger.info("╔═══════════════════════════════════════════════════════════")
    logger.info("║ 🚀 Приложение запускается...")
    logger.info("╚═══════════════════════════════════════════════════════════")
    
    # Инициализируем базу данных
    try:
        init_database()
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        raise
    
    # Очищаем папку с логами при каждом запуске
    try:
        clear_debug_logs()
    except Exception as e:
        logger.warning(f"⚠️ Не удалось очистить папку debug_logs: {e}. В облачной среде это нормально.")


@app.get("/", tags=["Root"])
def root():
    """Корневой эндпоинт для проверки доступности сервиса."""
    return {
        "status": "OK", 
        "message": "Beauty Salon AI Assistant is running",
        "version": "0.1.0",
        "database": "enabled"
    }


@app.post("/", tags=["Root"])
async def root_post(request: Request, background_tasks: BackgroundTasks):
    """
    POST обработчик для корневого пути.
    Может обрабатывать как обычные запросы, так и Telegram webhook.
    """
    try:
        # Пытаемся обработать как Telegram webhook
        update_data = await request.json()
        
        # Проверяем, что это Telegram update
        if "message" in update_data or "callback_query" in update_data:
            update = Update.parse_obj(update_data)
            background_tasks.add_task(process_telegram_update, update)
            return {"status": "ok"}
        else:
            # Если это не Telegram update, возвращаем обычный ответ
            return {
                "status": "OK", 
                "message": "Beauty Salon AI Assistant is running",
                "version": "0.1.0",
                "database": "enabled"
            }
    except Exception as e:
        logger.error(f"❌ Ошибка обработки POST запроса: {e}")
        # В случае ошибки возвращаем обычный ответ
        return {
            "status": "OK", 
            "message": "Beauty Salon AI Assistant is running",
            "version": "0.1.0",
            "database": "enabled"
        }


@app.get("/healthcheck", tags=["Health Check"])
def health_check():
    """Простой эндпоинт для проверки работоспособности сервиса."""
    return {
        "status": "OK",
        "database": "enabled",
        "webhook": "enabled"
    }
```

### Ключевые особенности:
- **Сервер:** Uvicorn (ASGI сервер для FastAPI)
- **Запуск:** `uvicorn app.main:app --host 0.0.0.0 --port 8080`
- **Startup события:**
  - Инициализация базы данных YDB
  - Очистка debug логов
- **Эндпоинты:**
  - `GET /` - корневой эндпоинт
  - `POST /` - обработка Telegram webhook (универсальный)
  - `GET /healthcheck` - health check для Yandex Cloud
  - `POST /telegram/{BOT_TOKEN}` - специфичный webhook для Telegram
  - `POST /telegram/webhook` - универсальный webhook для Telegram

---

## 3. 🔧 ENTRYPOINT СКРИПТ

**Статус:** ❌ Отдельный entrypoint скрипт НЕ используется

**Причина:** Используется прямой CMD в Dockerfile:
```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Инициализация при старте контейнера:**
- Выполняется автоматически через `@app.on_event("startup")` в `app/main.py`
- Логика инициализации находится в функции `startup_event()`

**Переменные окружения:**
- Загружаются через `load_dotenv()` в `app/main.py`
- Используется переменная `ENV_FILE` для указания пути к .env файлу (по умолчанию `.env`)
- Все переменные передаются через GitHub Secrets в workflow (см. раздел 5)

**Особенности:**
- В Serverless Container **НЕ** создаются файлы типа `key.json`
- Аутентификация в YDB происходит автоматически через IAM токены
- Google credentials загружаются через переменную окружения `GOOGLE_APPLICATION_CREDENTIALS` (может быть JSON строка)

---

## 4. 📦 REQUIREMENTS.TXT / PYPROJECT.TOML

**Расположение:** `pyproject.toml`  
**Менеджер зависимостей:** Poetry

```toml
[tool.poetry]
name = "beauty_salon_ai"
version = "0.1.0"
description = "AI-ассистент для салона красоты"
authors = []
# readme = "README.md"
packages = [{include = "app"}]

[tool.poetry.dependencies]
python = "^3.10"
fastapi = "^0.104.1"
uvicorn = {extras = ["standard"], version = "^0.24.0"}
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
python-dotenv = "^1.0.0"
sqlalchemy = "^2.0.23"
psycopg2-binary = "^2.9.9"
alembic = "^1.13.0"
httpx = "^0.25.0"
requests = "^2.31.0"
google-generativeai = "^0.8.0"
google-auth = "^2.23.0"
boto3 = "^1.40.0"
ydb = "^3.0.0"

[tool.poetry.group.dev.dependencies]
faker = "^21.0.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

**Установка зависимостей в Docker:**
```bash
poetry config virtualenvs.create false
poetry install --only=main --no-root --no-interaction --no-ansi --sync
```

---

## 5. 🔄 GITHUB ACTIONS WORKFLOW

**Расположение:** `.github/workflows/deploy-to-ycr.yml`

```yaml
name: Deploy to Yandex Cloud

on:
  push:
    branches:
      - main

jobs:
  build-and-deploy:
    name: Build and Deploy to Yandex Cloud
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Login to Yandex Container Registry
        uses: yc-actions/yc-cr-login@v1
        with:
          yc-sa-json-credentials: ${{ secrets.YC_SA_KEY }}

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push Docker image
        id: docker_build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            cr.yandex/${{ secrets.YC_REGISTRY_ID }}/beauty-salon-ai:${{ github.sha }}
            cr.yandex/${{ secrets.YC_REGISTRY_ID }}/beauty-salon-ai:latest
          platforms: linux/amd64

      - name: Deploy Serverless Container
        uses: yc-actions/yc-sls-container-deploy@v1
        with:
          yc-sa-json-credentials: ${{ secrets.YC_SA_KEY }}
          container-name: 'beauty-salon-container'
          folder-id: b1ged9dcl5dbfqojoa13
          revision-image-url: cr.yandex/${{ secrets.YC_REGISTRY_ID }}/beauty-salon-ai:${{ github.sha }}
          revision-service-account-id: 'aje7vj62jhsh2qjmuefm'
          revision-memory: '1GB'
          revision-execution-timeout: 20
          revision-env: |
            DATABASE_URL=${{ secrets.DATABASE_URL }}
            TELEGRAM_BOT_TOKEN=${{ secrets.TELEGRAM_BOT_TOKEN }}
            LLM_PROVIDER=${{ secrets.LLM_PROVIDER }}
            LOG_MODE=${{ secrets.LOG_MODE }}
            S3_ACCESS_KEY_ID=${{ secrets.S3_ACCESS_KEY_ID }}
            S3_SECRET_ACCESS_KEY=${{ secrets.S3_SECRET_ACCESS_KEY }}
            S3_BUCKET_NAME=${{ secrets.S3_BUCKET_NAME }}
            GOOGLE_APPLICATION_CREDENTIALS=${{ secrets.GOOGLE_APPLICATION_CREDENTIALS }}
            YANDEX_FOLDER_ID=${{ secrets.YANDEX_FOLDER_ID }}
            YANDEX_API_KEY_SECRET=${{ secrets.YANDEX_API_KEY_SECRET }}
            YDB_ENDPOINT=${{ secrets.YDB_ENDPOINT }}
            YDB_DATABASE=${{ secrets.YDB_DATABASE }}
```

### Параметры деплоя:
- **Container Registry URL:** `cr.yandex/{YC_REGISTRY_ID}/beauty-salon-ai:{TAG}`
- **Теги образа:**
  - `{github.sha}` - версия по коммиту
  - `latest` - последняя версия
- **Container name:** `beauty-salon-container`
- **Folder ID:** `b1ged9dcl5dbfqojoa13`
- **Service Account ID:** `aje7vj62jhsh2qjmuefm`
- **Memory:** `1GB`
- **Execution timeout:** `20` секунд
- **Platform:** `linux/amd64`

### GitHub Secrets (необходимые):
1. `YC_SA_KEY` - JSON ключ service account для доступа к Yandex Cloud
2. `YC_REGISTRY_ID` - ID Container Registry в Yandex Cloud
3. `DATABASE_URL` - URL базы данных (используется для PostgreSQL, но в проекте используется YDB)
4. `TELEGRAM_BOT_TOKEN` - токен Telegram бота
5. `LLM_PROVIDER` - провайдер LLM: "google" или "yandex"
6. `LOG_MODE` - режим логирования: "local" или "cloud"
7. `S3_ACCESS_KEY_ID` - ключ доступа к S3 (если LOG_MODE=cloud)
8. `S3_SECRET_ACCESS_KEY` - секретный ключ S3 (если LOG_MODE=cloud)
9. `S3_BUCKET_NAME` - имя S3 bucket (если LOG_MODE=cloud)
10. `GOOGLE_APPLICATION_CREDENTIALS` - JSON строка с Google credentials (если LLM_PROVIDER=google)
11. `YANDEX_FOLDER_ID` - ID папки в Yandex Cloud (если LLM_PROVIDER=yandex)
12. `YANDEX_API_KEY_SECRET` - API ключ YandexGPT (если LLM_PROVIDER=yandex)
13. `YDB_ENDPOINT` - endpoint YDB: `grpcs://ydb.serverless.yandexcloud.net:2135`
14. `YDB_DATABASE` - путь к базе данных YDB: `/ru-central1/{folder-id}/{database-id}`

---

## 6. 🔐 ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ

### Критичные (обязательные для запуска):

1. **YDB_ENDPOINT**
   - Описание: Endpoint для подключения к YDB
   - Значение по умолчанию: `grpcs://ydb.serverless.yandexcloud.net:2135`
   - Использование: `app/core/database.py`, `app/core/config.py`

2. **YDB_DATABASE**
   - Описание: Путь к базе данных YDB
   - Формат: `/ru-central1/{folder-id}/{database-id}`
   - Использование: `app/core/database.py`, `app/core/config.py`

3. **TELEGRAM_BOT_TOKEN**
   - Описание: Токен Telegram бота
   - Использование: `app/core/config.py`, `app/api/telegram.py`

4. **LLM_PROVIDER**
   - Описание: Провайдер LLM: "google" или "yandex"
   - Значение по умолчанию: `"yandex"`
   - Использование: `app/core/config.py`, `app/services/llm_service.py`

### Опциональные (в зависимости от выбранного провайдера):

#### Для Google (LLM_PROVIDER=google):

5. **GOOGLE_APPLICATION_CREDENTIALS**
   - Описание: JSON строка с credentials или путь к файлу
   - Формат: JSON строка или путь к файлу
   - Использование: `app/services/llm_service.py`
   - Варианты загрузки:
     - JSON строка в переменной окружения
     - Путь к JSON файлу
     - Application Default Credentials (ADC) - автоматически в Cloud

6. **GOOGLE_APPLICATION_CREDENTIALS_JSON** (альтернатива)
   - Описание: JSON строка с credentials (приоритет выше)
   - Использование: `app/services/llm_service.py`

#### Для YandexGPT (LLM_PROVIDER=yandex):

7. **YANDEX_FOLDER_ID**
   - Описание: ID папки в Yandex Cloud
   - Использование: `app/core/config.py`, `app/services/llm_service.py`

8. **YANDEX_API_KEY_SECRET**
   - Описание: API ключ для YandexGPT
   - Использование: `app/core/config.py`, `app/services/llm_service.py`

9. **YANDEX_MODEL_VERSION** (опционально)
   - Описание: Версия модели YandexGPT
   - Значение по умолчанию: `"yandexgpt-pro/latest"`
   - Возможные значения: `"yandexgpt"`, `"yandexgpt-pro/latest"`, `"yandexgpt-pro/5.1"`
   - Использование: `app/core/config.py`

#### Для логирования:

10. **LOG_MODE**
    - Описание: Режим логирования
    - Значение по умолчанию: `"local"`
    - Возможные значения: `"local"`, `"cloud"`
    - Использование: `app/core/config.py`

#### Для облачного логирования (LOG_MODE=cloud):

11. **S3_ACCESS_KEY_ID**
    - Описание: Access key для Yandex Object Storage
    - Использование: `app/core/config.py`, `app/services/s3_logger_service.py`

12. **S3_SECRET_ACCESS_KEY**
    - Описание: Secret key для Yandex Object Storage
    - Использование: `app/core/config.py`, `app/services/s3_logger_service.py`

13. **S3_BUCKET_NAME**
    - Описание: Имя bucket в Yandex Object Storage
    - Использование: `app/core/config.py`, `app/services/s3_logger_service.py`

14. **S3_ENDPOINT_URL** (опционально)
    - Описание: Endpoint URL для S3
    - Значение по умолчанию: `"https://storage.yandexcloud.net"`
    - Использование: `app/core/config.py`

#### Для ChromaDB (опционально):

15. **CHROMA_HOST**
    - Описание: Хост для ChromaDB (если используется серверный режим)
    - Использование: `app/core/vector_store_client.py`
    - Примечание: Если не указан, используется локальное хранилище

#### Для конфигурации (опционально):

16. **ENV_FILE**
    - Описание: Путь к файлу с переменными окружения
    - Значение по умолчанию: `".env"`
    - Использование: `app/main.py`, `app/core/config.py`

17. **LOG_LEVEL**
    - Описание: Уровень логирования
    - Значение по умолчанию: `"INFO"`
    - Использование: `app/main.py`

### PORT (особый случай):

**Статус:** ❌ Переменная `PORT` **НЕ используется**

**Причина:** Порт захардкожен в Dockerfile:
```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Использование порта:**
- Порт **8080** фиксированный
- Yandex Cloud Serverless Container автоматически направляет трафик на этот порт
- Нет необходимости в переменной окружения `PORT`

---

## 7. ⚙️ ОСОБЕННОСТИ КОНФИГУРАЦИИ КОНТЕЙНЕРА

### Режим работы:
- **Тип:** HTTP-сервер (FastAPI/ASGI)
- **Протокол:** HTTP/HTTPS
- **Поддержка:** Telegram Webhook, Health Check, REST API

### Порт приложения:
- **Порт:** `8080`
- **Host:** `0.0.0.0` (слушает на всех интерфейсах)
- **EXPOSE:** Не указан в Dockerfile (Yandex Cloud автоматически определяет)

### Health Check:
- **Эндпоинт:** `GET /healthcheck`
- **Ответ:**
  ```json
  {
    "status": "OK",
    "database": "enabled",
    "webhook": "enabled"
  }
  ```
- **Использование:** Yandex Cloud автоматически проверяет этот эндпоинт

### Специальные настройки Yandex Cloud:

1. **Service Account:**
   - ID: `aje7vj62jhsh2qjmuefm`
   - Использование: Автоматическая аутентификация для YDB и других сервисов Yandex Cloud

2. **Memory:**
   - Выделено: `1GB`
   - Настройка в workflow: `revision-memory: '1GB'`

3. **Execution Timeout:**
   - Таймаут: `20` секунд
   - Настройка в workflow: `revision-execution-timeout: 20`

4. **Аутентификация:**
   - **YDB:** Автоматическая через IAM токены (не требуется key.json)
   - **Google Cloud:** Через `GOOGLE_APPLICATION_CREDENTIALS` (JSON строка или ADC)
   - **YandexGPT:** Через `YANDEX_API_KEY_SECRET`

5. **Сеть:**
   - Входящий трафик: Автоматически направляется на порт 8080
   - Исходящий трафик: Разрешен для доступа к внешним API (Telegram, Google, Yandex)

### Структура эндпоинтов:

1. **GET /** - Корневой эндпоинт (статус сервиса)
2. **POST /** - Универсальный webhook (принимает Telegram updates)
3. **GET /healthcheck** - Health check для Yandex Cloud
4. **POST /telegram/{BOT_TOKEN}** - Специфичный webhook для Telegram
5. **POST /telegram/webhook** - Универсальный webhook для Telegram

---

## 8. 📁 СТРУКТУРА ПРОЕКТА

### Файлы/папки, копируемые в Docker образ:

Из Dockerfile:
```dockerfile
COPY app ./app                    # Весь код приложения
COPY dialogue_patterns.json .     # Конфигурация паттернов диалога
COPY scripts ./scripts             # Вспомогательные скрипты
```

### Файлы/папки, исключаемые из образа (.dockerignore):

```dockerignore
# Исключаем виртуальные окружения
.venv
venv

# Исключаем кэш Python
__pycache__/
*.pyc
*.pyo

# Исключаем системные и IDE-файлы
.git
.gitignore
.dockerignore
*.md
.idea/
.vscode/

# Исключаем локальные базы данных и логи
/chroma_db_local/
/debug_logs/

# Исключаем файлы окружения
.env

# Исключаем папку с редактором
/editor/
```

### Полная структура копируемых файлов:

```
/app/
├── app/                          # Основное приложение
│   ├── __init__.py
│   ├── main.py                   # Точка входа FastAPI
│   ├── api/                      # API роутеры
│   │   ├── __init__.py
│   │   └── telegram.py           # Telegram webhook handlers
│   ├── core/                     # Ядро приложения
│   │   ├── __init__.py
│   │   ├── config.py             # Конфигурация
│   │   ├── database.py           # YDB подключение
│   │   ├── logging_config.py     # Настройка логирования
│   │   └── vector_store_client.py # ChromaDB клиент
│   ├── models/                   # SQLAlchemy модели
│   ├── repositories/             # Репозитории для работы с БД
│   ├── schemas/                  # Pydantic схемы
│   ├── services/                 # Бизнес-логика
│   └── utils/                    # Утилиты
├── dialogue_patterns.json        # Паттерны диалогов
└── scripts/                      # Вспомогательные скрипты
```

### Файлы, НЕ включаемые в образ:

- `key.json` - ключи сервисного аккаунта (не нужны, используется IAM)
- `.env` - переменные окружения (передаются через GitHub Secrets)
- `*.db`, `*.sqlite` - локальные базы данных
- `debug_logs/` - локальные логи
- `/editor/` - веб-редактор (отдельное приложение)
- Документация (`*.md`)
- Тестовые данные

---

## 9. 🔄 ПРОЦЕСС ДЕПЛОЯ

### Автоматический деплой (через GitHub Actions):

1. **Триггер:** Push в ветку `main`
2. **Сборка образа:**
   - Использует Docker Buildx для multi-platform сборки
   - Платформа: `linux/amd64`
   - Теги: `{sha}` и `latest`
3. **Загрузка в Registry:**
   - Registry: `cr.yandex/{YC_REGISTRY_ID}/beauty-salon-ai`
   - Аутентификация через `YC_SA_KEY`
4. **Деплой контейнера:**
   - Обновление revision в Serverless Container
   - Передача всех переменных окружения
   - Применение настроек (memory, timeout)

### Ручной деплой (альтернатива):

1. **Сборка образа:**
   ```bash
   docker build -t beauty-salon-ai .
   ```

2. **Тегирование:**
   ```bash
   docker tag beauty-salon-ai cr.yandex/{YC_REGISTRY_ID}/beauty-salon-ai:latest
   ```

3. **Загрузка в Registry:**
   ```bash
   yc container registry configure-docker
   docker push cr.yandex/{YC_REGISTRY_ID}/beauty-salon-ai:latest
   ```

4. **Деплой через Yandex Cloud CLI:**
   ```bash
   yc serverless container revision deploy \
     --container-name beauty-salon-container \
     --image cr.yandex/{YC_REGISTRY_ID}/beauty-salon-ai:latest \
     --memory 1GB \
     --cores 1 \
     --execution-timeout 20s \
     --service-account-id aje7vj62jhsh2qjmuefm \
     --environment TELEGRAM_BOT_TOKEN=...,YDB_ENDPOINT=...
   ```

---

## 10. ✅ ЧЕКЛИСТ ДЛЯ НОВОГО ПРОЕКТА

### Обязательные шаги:

- [ ] Создать Dockerfile по образцу (с multi-stage build)
- [ ] Создать `app/main.py` с FastAPI приложением
- [ ] Настроить `pyproject.toml` с зависимостями
- [ ] Настроить `.dockerignore`
- [ ] Создать GitHub Actions workflow `.github/workflows/deploy-to-ycr.yml`
- [ ] Настроить GitHub Secrets:
  - [ ] `YC_SA_KEY`
  - [ ] `YC_REGISTRY_ID`
  - [ ] `TELEGRAM_BOT_TOKEN`
  - [ ] `YDB_ENDPOINT`
  - [ ] `YDB_DATABASE`
  - [ ] `LLM_PROVIDER`
  - [ ] Остальные в зависимости от выбранного провайдера
- [ ] Настроить Service Account в Yandex Cloud
- [ ] Создать Serverless Container в Yandex Cloud
- [ ] Настроить health check эндпоинт `/healthcheck`
- [ ] Убедиться, что порт 8080 используется в CMD

### Опциональные шаги:

- [ ] Настроить S3 для логирования (если LOG_MODE=cloud)
- [ ] Настроить ChromaDB (если используется)
- [ ] Добавить мониторинг и алертинг
- [ ] Настроить автоскейлинг контейнера

---

## 11. 📝 ЗАМЕТКИ И ВАЖНЫЕ МОМЕНТЫ

### Особенности аутентификации:

1. **YDB:**
   - В Serverless Container используется автоматическая аутентификация через IAM
   - НЕ требуется файл `key.json`
   - НЕ требуется `YC_SA_JSON_CREDENTIALS` (используется service account контейнера)

2. **Google Cloud:**
   - Поддерживает 3 варианта загрузки credentials
   - В Cloud может использоваться Application Default Credentials
   - Для локальной разработки нужен файл или JSON строка

3. **YandexGPT:**
   - Требует только API ключ (`YANDEX_API_KEY_SECRET`)
   - Не требует сложной настройки credentials

### Обработка ошибок:

- При ошибке инициализации БД приложение **падает** (raise в startup)
- При ошибке очистки логов - только warning (не критично)
- Health check всегда возвращает 200 OK (если приложение запущено)

### Производительность:

- Memory: 1GB (можно увеличить при необходимости)
- Timeout: 20 секунд (достаточно для обработки Telegram webhook)
- Пул сессий YDB создается автоматически
- Используется асинхронная обработка через FastAPI

---

## 12. 🔗 ССЫЛКИ НА КЛЮЧЕВЫЕ ФАЙЛЫ

- **Dockerfile:** `./Dockerfile`
- **Главный файл:** `./app/main.py`
- **Конфигурация:** `./app/core/config.py`
- **База данных:** `./app/core/database.py`
- **API роутеры:** `./app/api/telegram.py`
- **Зависимости:** `./pyproject.toml`
- **Workflow:** `./.github/workflows/deploy-to-ycr.yml`
- **Пример env:** `./env.example`
- **Docker ignore:** `./.dockerignore`

---

**Конец отчета**

