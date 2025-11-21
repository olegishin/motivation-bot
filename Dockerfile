# Используем официальный образ Python 3.11
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Настраиваем переменные окружения для корректного вывода логов и часового пояса
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Kiev

# Устанавливаем пакет tzdata для работы с часовыми поясами
RUN apt-get update && apt-get install -y tzdata && apt-get clean && rm -rf /var/lib/apt/lists/*

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN python -m pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Копируем контент из локальной папки 'data_initial'
COPY data_initial/ /app/data_initial/

# Копируем ВСЮ папку 'bot'
COPY bot/ /app/bot/

# ✅ НОВОЕ: Явно копируем шаблоны (на всякий случай, хотя COPY bot/ должно хватить, но так надежнее)
COPY bot/templates/ /app/bot/templates/

# Эта команда CMD соответствует тому, что ожидает fly.toml
# (Uvicorn будет запущен из /app/bot, поэтому путь "main:app" - верный)
WORKDIR /app/bot
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]