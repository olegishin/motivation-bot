import os
import json
import random

FILES = [
    "fotinia_morning_phrases.json",
    "fotinia_day_phrases.json",
    "fotinia_evening_phrases.json",
    "fotinia_goals.json",
    "fotinia_phrases.json",
    "challenges.json",
    "universe_laws.json"
]

def load_json_file(filename):
    """Загружает JSON-файл и возвращает список, либо пустой список при ошибке."""
    try:
        path = os.path.join(os.path.dirname(__file__), filename)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"❌ Ошибка загрузки {filename}: {e}")
        return []

def test_files(files):
    for f in files:
        data = load_json_file(f)
        if data:
            print(f"✅ {f}: {len(data)} элементов, пример → {random.choice(data)}")
        else:
            print(f"⚠️ {f} пустой или некорректный")

if __name__ == "__main__":
    test_files(FILES)
