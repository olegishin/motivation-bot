from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_keyboard(language='ru'):
    """Главное меню (Reply кнопки) с поддержкой языков."""
    labels = {
        'ru': ["💪 Мотивируй меня", "🎵 Ритм дня", "⚔️ Челлендж дня", "📜 Правила Вселенной", "👤 Профиль", "⚙️ Настройки"],
        'uk': ["💪 Мотивуй мене", "🎵 Ритм дня", "⚔️ Челендж дня", "📜 Правила Всесвіту", "👤 Профіль", "⚙️ Налаштування"],
        'en': ["💪 Motivate me", "🎵 Rhythm of the day", "⚔️ Daily Challenge", "📜 Rules of Universe", "👤 Profile", "⚙️ Settings"]
    }
    
    # Берем кнопки для языка, или русские по умолчанию
    btns = labels.get(language, labels['ru'])
    
    # Строим клавиатуру: 2 кнопки в ряд
    kb = [
        [KeyboardButton(text=btns[0]), KeyboardButton(text=btns[1])],
        [KeyboardButton(text=btns[2]), KeyboardButton(text=btns[3])],
        [KeyboardButton(text=btns[4]), KeyboardButton(text=btns[5])]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def language_keyboard():
    """Клавиатура выбора языка (Reply)."""
    kb = [
        [KeyboardButton(text="Українська"), KeyboardButton(text="English")],
        [KeyboardButton(text="Русский")],
        [KeyboardButton(text="🔙 Back / Назад")] 
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)