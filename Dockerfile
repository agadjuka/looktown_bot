FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Системные зависимости по-минимуму (для ydb и SSL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Зависимости Python
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Исходники приложения
COPY bot.py ./
COPY main.py ./
COPY service_factory.py ./
COPY src ./src

# Запуск через uvicorn напрямую (как в рабочем проекте)
# Порт 8080 захардкожен (Yandex Cloud автоматически определит)
# key.json создается в startup событии FastAPI при необходимости
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]


