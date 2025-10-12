# ---- Базовий Python ----
FROM python:3.11-slim

# ---- Системна підготовка ----
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8080

# ---- Залежності ----
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Копіюємо код ----
COPY . .

# ---- Переносимо JSON-файли у /data ----
RUN mkdir -p /data && cp -r *.json /data/ || echo "No JSON files found"

# ---- Запуск через Uvicorn ----
EXPOSE 8080
CMD ["uvicorn", "fotinia_bot:app", "--host", "0.0.0.0", "--port", "8080"]
