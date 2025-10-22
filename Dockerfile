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

# ✅ ГЛАВНОЕ ИСПРАВЛЕНИЕ:
# Копируем контент из локальной папки 'data_initial' (где лежат ваши файлы)
# внутрь образа, чтобы потом перенести его в постоянное хранилище.
COPY data_initial/ /app/data_initial/

# Копируем основной файл бота
COPY bot.py .

# Команда для запуска веб-сервера с ботом
CMD ["uvicorn", "bot:app", "--host", "0.0.0.0", "--port", "8080"]