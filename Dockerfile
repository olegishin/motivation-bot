# Используем официальный Python 3.11
FROM python:3.11-slim

WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .
EXPOSE 8443

# Запуск бота
CMD ["python", "fotinia_bot.py"]
