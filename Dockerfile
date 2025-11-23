FROM python:3.11-slim

# 1. Рабочая директория - КОРЕНЬ проекта
WORKDIR /app

# 2. Настройки окружения и часовой пояс (твои настройки)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Kiev

# 3. Установка системных пакетов (tzdata нужна для TZ=Europe/Kiev)
RUN apt-get update && apt-get install -y tzdata && apt-get clean && rm -rf /var/lib/apt/lists/*

# 4. Зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем ВЕСЬ проект (и bot, и config.py, и data_initial)
COPY . .

# 6. Создаем папку для базы данных (важно для Fly.io volumes)
RUN mkdir -p data

# 7. Запуск от корня. Обращаемся к bot.main
CMD ["uvicorn", "bot.main:app", "--host", "0.0.0.0", "--port", "8080"]