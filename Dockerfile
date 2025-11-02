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

# Стартовый скрипт, который создаст key.json из секрета только в рантайме
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Порт не обязателен для Telegram-поллинга, но оставим для совместимости
EXPOSE 8080

CMD ["/app/entrypoint.sh"]


