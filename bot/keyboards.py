from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from localization import t

# --- ГЛАВНОЕ МЕНЮ (REPLY) ---
def main_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    labels = {
        'ru': ["💪 Мотивируй меня", "🎵 Ритм дня", "📜 Правила Вселенной", "⚔️ Челлендж дня", "👤 Профиль", "📊 Статистика", "⚙️ Настройки"],
        'uk': ["💪 Мотивуй мене", "🎵 Ритм дня", "📜 Правила Всесвіту", "⚔️ Челендж дня", "👤 Профіль", "📊 Статистика", "⚙️ Налаштування"],
        'en': ["💪 Motivate me", "🎵 Rhythm of the day", "📜 Rules of Universe", "⚔️ Daily Challenge", "👤 Profile", "📊 Statistics", "⚙️ Settings"]
    }
    # Если язык не найден, берем русский
    btns = labels.get(lang, labels['ru'])
    
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=btns[0]), KeyboardButton(text=btns[1]))
    builder.row(KeyboardButton(text=btns[2]), KeyboardButton(text=btns[3]))
    builder.row(KeyboardButton(text=btns[4]), KeyboardButton(text=btns[5]))
    builder.row(KeyboardButton(text=btns[6]))
    
    return builder.as_markup(resize_keyboard=True)

# --- АЛИАСЫ (для совместимости) ---
def get_main_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    return main_menu_keyboard(lang)

def get_reply_keyboard_for_user(chat_id: int, lang: str, user_data: dict) -> ReplyKeyboardMarkup:
    return main_menu_keyboard(lang)

def get_cancel_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=t('cmd_cancel', lang)))
    return builder.as_markup(resize_keyboard=True)

def get_cooldown_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=t('btn_settings', lang)))
    return builder.as_markup(resize_keyboard=True)

# --- ИНЛАЙН КЛАВИАТУРЫ (Те самые, которых не хватало) ---

def get_inline_feedback_keyboard(category: str) -> InlineKeyboardMarkup:
    """Клавиатура лайк/дизлайк"""
    builder = InlineKeyboardBuilder()
    builder.button(text="👍", callback_data=f"reaction:like:{category}")
    builder.button(text="👎", callback_data=f"reaction:dislike:{category}")
    builder.adjust(2)
    return builder.as_markup()

# Алиасы для обратной связи
def get_broadcast_keyboard(category: str = "mixed", lang: str = "ru", current_text: str = "") -> InlineKeyboardMarkup:
    return get_inline_feedback_keyboard(category)

def get_on_demand_keyboard(category: str = "mixed", lang: str = "ru", current_text: str = "") -> InlineKeyboardMarkup:
    return get_inline_feedback_keyboard(category)

def get_challenge_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура челленджа"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Принять вызов", callback_data="challenge_accept")
    builder.button(text="🔄 Другой вариант", callback_data="challenge_new")
    builder.adjust(1)
    return builder.as_markup()

def get_payment_keyboard(lang: str = "ru", is_test_user: bool = False, show_new_demo: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура для оплаты Premium"""
    builder = InlineKeyboardBuilder()
    builder.button(text=t('btn_pay_premium', lang), callback_data="pay_premium")
    if is_test_user:
        builder.button(text=t('btn_pay_api_test_premium', lang), callback_data="pay_api_test")
    if show_new_demo:
         builder.button(text=t('btn_want_demo', lang), callback_data="activate_new_demo")
    builder.adjust(1)
    return builder.as_markup()

def get_settings_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Язык / Language", callback_data="settings_lang")
    builder.button(text="⏰ Часовой пояс / Timezone", callback_data="settings_tz")
    builder.adjust(1)
    return builder.as_markup()

def get_language_keyboard(current_lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    builder.button(text="🇺🇦 Українська", callback_data="set_lang_ua")
    builder.button(text="🇬🇧 English", callback_data="set_lang_en")
    builder.adjust(3)
    return builder.as_markup()

def get_profile_keyboard(lang: str = "ru", is_paid: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для страницы профиля."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Сменить язык", callback_data="settings_lang")
    builder.button(text="⏰ Сменить часовой пояс", callback_data="settings_tz")
    if not is_paid:
        builder.button(text="💎 Premium", callback_data="go_to_payment")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def get_timezone_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Москва (+3)", callback_data="tz_Europe/Moscow")
    builder.button(text="Киев (+2)", callback_data="tz_Europe/Kiev")
    builder.button(text="Лондон (+0)", callback_data="tz_Europe/London")
    builder.adjust(2, 1)
    return builder.as_markup()