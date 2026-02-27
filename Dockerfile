FROM python:3.11-slim

WORKDIR /app

# Оптимизация + часовой пояс
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Kiev

# Установка tzdata и build-essential (на всякий случай)
RUN apt-get update && apt-get install -y \
    tzdata \
    build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . .

# Создаём папку для данных (абсолютный путь — надёжнее)
RUN mkdir -p /app/data

# Открываем порт (Fly.io сам маппит, но указать полезно)
EXPOSE 8080

# Запуск — Uvicorn + правильный модуль
CMD ["uvicorn", "bot.main:app", "--host", "0.0.0.0", "--port", "8080"]