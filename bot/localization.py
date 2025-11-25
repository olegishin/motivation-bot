# 2 - bot/localization.py 
# Локализация и переводы.

from typing import Literal, Dict

# ✅ ИСПРАВЛЕНИЕ: Добавлен префикс bot.
from bot.config import settings, logger 

# Типизация для языков
Lang = Literal["ru", "ua", "en"]

# Берем язык по умолчанию из settings
DEFAULT_LANG = settings.DEFAULT_LANG 

COMMON_LANG_CHOOSE_FIRST = "Вітаю! Будь ласка, оберіть мову: 👇\n\nEnglish: Please select a language: 👇\n\nЗдравствуйте! Пожалуйста, выберите язык: 👇"

# --- 🌐 Глобальный словарь переводов ---
translations: Dict[Lang, Dict[str, str]] = {
    "ru": {
        "lang_choose_first": COMMON_LANG_CHOOSE_FIRST,
        "welcome": "🌟 Привет, {name}! Я Фотиния, твой бот-помощник по саморазвитию.\n\nЯ буду присылать тебе сообщения 4 раза в день, чтобы помочь держать фокус. У тебя есть ознакомительный период ({demo_days} дня), чтобы попробовать все функции. Начнем! 👇",
        "welcome_return": "🌟 С возвращением, {name}! Рад снова тебя видеть. Твой {status_text} доступ активен. Используй кнопки ниже 👇",
        "welcome_renewed_demo": "🌟 {name}, с возвращением! У Вас новый демо-период на {demo_days} дней. Все функции возобновлены. Достигнутые ранее уровни сброшены. В добрый путь! 👇",
        
        "welcome_timezone_note": "\n\nP.S. Ваш часовой пояс был автоматически установлен: <code>{default_tz}</code>. Если он неверный, используйте команду /timezone, чтобы его изменить.",
        "timezone_command_text": "⚙️ <b>Настройка часового пояса</b>\n\nВаш текущий пояс: <code>{user_tz}</code>\n\nЧтобы изменить его, <b>отправьте свой часовой пояс</b> в формате IANA (TZ Database).\n\nНапример:\n<code>Europe/Berlin</code>\n<code>Europe/Warsaw</code>\n<code>America/New_York</code>\n<code>Asia/Tbilisi</code>\n\nОтправьте /cancel для отмены.",
        "timezone_set_success": "✅ Часовой пояс обновлен на <code>{new_tz}</code>.",
        "timezone_set_error": "⚠️ Ошибка. <code>{error_text}</code> - это невалидный часовой пояс. Попробуйте еще раз (например, <code>Europe/Kiev</code>) или нажмите /cancel.",
        "timezone_cancel": "✅ Настройка отменена. Ваш часовой пояс остался: <code>{user_tz}</code>.",
        "cmd_cancel": "Отмена",
        "admin_grant_success": "✅ Premium-доступ успешно выдан пользователю {name} (ID: {user_id}).",
        "admin_grant_fail_id": "⚠️ Ошибка. Пользователь с ID <code>{user_id}</code> не найден.",
        "admin_grant_fail_already_paid": "⚠️ Пользователь {name} (ID: {user_id}) уже имеет Premium-доступ.",
        "admin_grant_usage": "⚠️ Неверный формат. Используйте: <code>/grant [ID_пользователя]</code>",
        "user_grant_notification": "🎉 <b>Доступ активирован!</b>\n\nАдминистратор активировал ваш Premium-доступ. Поздравляем!\n\nНажмите /start, чтобы обновить клавиатуру.",
        
        "demo_expiring_soon_h": "🔒 {name}, ваш демо-доступ истекает менее чем через {hours} час(а). Не забудьте активировать подписку, чтобы не терять прогресс!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Ваш демо-доступ закончился.</b>\n\nДо возобновления демо-периода осталось **{hours} ч. {minutes} мин.**\n\nВы также можете активировать Premium-доступ прямо сейчас, нажав кнопку '👑 Хочу Premium'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Ваш демо-доступ закончился.</b>\n\nВы можете активировать **еще один** пробный период ({demo_days} дня) или получить постоянный Premium-доступ.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Ваши пробные периоды закончились.</b>\n\nДля возобновления доступа, пожалуйста, активируйте Premium-подписку. 👇",
        "demo_awaiting_renewal": "Понял. Ваш демо-период возобновится через **{hours} ч. {minutes} мин.**\n\nВ режиме ожидания рассылки отключены, но вы можете активировать Premium в любой момент.",
        "pay_info": "💳 Для получения полного доступа, пожалуйста, свяжитесь с администратором.",
        "pay_instructions": "✅ {name}, добро пожаловать в Premium! Я буду Вашей поддержкой в течение 30 дней. За это время Вы получите 120 сообщений (это ~2 грн за сообщение).\n\nДля активации, пожалуйста, переведите **245 грн** на эту Банку Monobank:\n\n`https://send.monobank.ua/jar/ao8c487LS`\n\n**ВАЖНО:** После оплаты, пожалуйста, пришлите скриншот чека нашему менеджеру: **@fotinia_admin**. Он увидит его и активирует ваш доступ вручну.",
        "pay_api_success_test": "✅ {name}, добро пожаловать в Premium! (Тест API)\nЯ буду Вашей поддержкой в течение 30 дней. За это время Вы получите 120 сообщений (это ~2 грн за сообщение). Нажмите /start.",
        
        # --- ИСПРАВЛЕНИЯ РЕАКЦИЙ И ШАРИНГА (Новые ключи) ---
        "share_text_template": "Посмотри, какой бот мне помогает двигаться к цели! @{bot_username}", 
        "reaction_received": "Благодарю за твою реакцию, {name}!", 
        "reaction_already_accepted": "{name}, твоя информация уже принята.",
        "share_text_full": "Посмотри, какое сообщение сегодня прислал мне мой бот, который помогает мне быть на позитиве и двигаться к цели!\nПопробуй и ты, это интересно :-)\n@{bot_username}",
        "share_text_with_quote": "🔥 {quote}\n\nПосмотри, какое сообщение сегодня прислал мне мой бот, который помогает мне быть на позитиве и двигаться к цели!\nПопробуй и ты, это интересно :-)\n@{bot_username}",
        
        "profile_title": "👤 <b>Ваш профиль:</b>",
        "profile_name": "📛 Имя",
        "profile_challenges_accepted": "⚔️ Принято челленджей",
        "profile_challenges_completed": "✅ Выполнено",
        "profile_challenge_streak": "🔥 Серия выполнений",
        "profile_status": "💰 Статус",
        "profile_likes": "👍 Лайки",
        "profile_dislikes": "👎 Дизлайки",
        "status_premium": "⭐ Premium",
        "status_demo": "🆓 Демо",
        "list_empty": "⚠️ Список для '{title}' пуст.",
        "list_error_format": "⚠️ Ошибка форматирования текста для '{title}'. Отсутствует ключ: {e}",
        "list_error_index": "⚠️ Произошла ошибка при выборе элемента из списка '{title}'. Список может быть пуст.",
        "list_error_unexpected": "⚠️ Произошла непредвиденная ошибка при отправке '{title}'.",
        "list_error_data": "⚠️ Ошибка данных для '{title}'. Обратитесь к администратору.",
        "challenge_already_issued": "⏳ Вы уже приняли челлендж на сегодня.",
        "challenge_pending_acceptance": "🔥 У вас уже есть активный челлендж. Примите его или нажмите 'Новый' в сообщении выше.",
        "challenge_accepted_msg": "💪 <b>Челлендж принят:</b>\n\n<i>{challenge_text}</i>",
        "challenge_completed_msg": "✅ Отлично! Челлендж выполнен!",
        "challenge_completed_edit_err": "⚠️ Не удалось отредактировать сообщение о выполнении.",
        "challenge_new_day": "⚔️ <b>Челлендж дня:</b>\n{challenge_text}",
        "challenge_choose_error": "⚠️ Ошибка при выборе челленджа. Список может быть пустым.",
        "challenge_button_error": "⚠️ Произошла ошибка при формировании кнопок челленджа.",
        "challenge_unexpected_error": "⚠️ Произошла непредвиденная ошибка при отправке челленджа.",
        "challenge_accept_error": "⚠️ Произошла ошибка при принятии челленджа. Попробуйте запросить челлендж заново.",
        "challenge_streak_3_level_1": "🔥🔥🔥 {name}, ты молодец! Выполнено 3 челленджа подряд, и достигнут 1 уровень. Продолжай в том же темпе, и тебя ждет награда!",
        "unknown_command": "❓ Неизвестная команда. Пожалуйста, используйте кнопки.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "Файл users.json ещё не создан или пуст.",
        "reload_confirm": "✅ Кэш и задачи планировщика обновлены!",
        "start_required": "Похоже, мы ещё не знакомы. Пожалуйста, нажмите /start, чтобы начать.",
        "admin_new_user": "🎉 Новый пользователь: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Показать статистику",
        "admin_bot_started": "🤖 Бот успешно запущен (v10.17 - Refactored)",
        "admin_bot_stopping": "⏳ Бот останавливается...",
        "lang_choose": "Выберите язык: 👇",
        "lang_chosen": "✅ Язык установлен на Русский.",
        
        # --- КНОПКИ ---
        "btn_motivate": "💪 Мотивируй меня", "btn_rhythm": "🎵 Ритм дня",
        "btn_challenge": "⚔️ Челлендж дня", "btn_rules": "📜 Правила Вселенной",
        "btn_profile": "👤 Профиль",
        "btn_share": "💌 Поделиться",
        "btn_show_users": "📂 Смотреть users.json", "btn_stats": "📊 Статистика",
        "btn_reload_data": "🔄 Обновить",
        "btn_pay_premium": "👑 Хочу Premium",
        "btn_pay_api_test_premium": "👑 Premium (API Тест)",
        "btn_want_demo": "🔄 Хочу демо",
        "btn_challenge_accept": "✅ Принять", "btn_challenge_new": "🎲 Новый",
        "btn_challenge_complete": "✅ Выполнено",
        
        # ✅ ДОБАВЛЕНО ДЛЯ НАСТРОЕК
        "btn_settings": "⚙️ Настройки",
        "btn_back": "↩️ Назад",
        "msg_choose_action": "Выберите действие:",
        "msg_welcome_back": "🏠 Вы вернулись в главное меню",

        "title_motivation": "💪", "title_rhythm": "🎶 Ритм дня:", "title_rules": "📜 Правила Вселенной",
        "title_rules_daily": "📜 <b>{title} ({count}/{limit}):</b>",
        "rules_limit_reached": "На сегодня это все законы. Новые ты узнаешь завтра! 🌙",
        "profile_status_total": "Всего",
        "profile_status_active": "Активных",
        "profile_status_first_time": "Первый раз",
        "profile_status_repeat": "Повторно",
        "profile_status_inactive": "Неактивных",
        "profile_status_demo_expired": "Закончилось демо",
        "profile_status_blocked": "Заблокировали",
    },
    "ua": {
        "lang_choose_first": COMMON_LANG_CHOOSE_FIRST,
        "welcome": "🌟 Привіт, {name}! Я бот Фотінія, твій особистий помічник із саморозвитку.\n\nЯ буду надсилати тобі повідомлення 4 рази на день, щоб допомогти тримати фокус. У тебе є ознайомчий період ({demo_days} дні), щоб спробувати всі функції. Почнемо! 👇",
        "welcome_return": "🌟 З поверненням, {name}! Радий знову тебе бачити. Твій {status_text} доступ активний. Використовуй кнопки нижче 👇",
        "welcome_renewed_demo": "🌟 {name}, з поверненням! У Вас новий демо-період на {demo_days} днів. Всі функції відновлено. Досягнуті раніше рівні скинуті. В добру путь! 👇",
        
        "welcome_timezone_note": "\n\nP.S. Ваш часовий пояс було автоматично встановлено: <code>{default_tz}</code>. Якщо він невірний, використовуйте команду /timezone, щоб його змінити.",
        "timezone_command_text": "⚙️ <b>Налаштування часового поясу</b>\n\nВаш поточний пояс: <code>{user_tz}</code>\n\nЩоб змінити його, <b>надішліть свій часовий пояс</b> у форматі IANA (TZ Database).\n\nНаприклад:\n<code>Europe/Berlin</code>\n<code>Europe/Warsaw</code>\n<code>America/New_York</code>\n<code>Asia/Tbilisi</code>\n\nНадішліть /cancel для скасування.",
        "timezone_set_success": "✅ Часовий пояс оновлено на <code>{new_tz}</code>.",
        "timezone_set_error": "⚠️ Помилка. <code>{error_text}</code> - це невалідний часовий пояс. Спробуйте ще раз (наприклад, <code>Europe/Kiev</code>) або натисніть /cancel.",
        "timezone_cancel": "✅ Налаштування скасовано. Ваш часовий пояс залишився: <code>{user_tz}</code>.",
        "cmd_cancel": "Скасувати",
        "admin_grant_success": "✅ Premium-доступ успішно видано користувачу {name} (ID: {user_id}).",
        "admin_grant_fail_id": "⚠️ Помилка. Користувача з ID <code>{user_id}</code> не знайдено.",
        "admin_grant_fail_already_paid": "⚠️ Користувач {name} (ID: {user_id}) вже має Premium-доступ.",
        "admin_grant_usage": "⚠️ Невірний формат. Використовуйте: <code>/grant [ID_користувача]</code>",
        "user_grant_notification": "🎉 <b>Доступ активовано!</b>\n\nАдміністратор активував ваш Premium-доступ. Вітаємо!\n\nНатисніть /start, щоб оновити клавіатуру.",
        
        "demo_expiring_soon_h": "🔒 {name}, ваш демо-доступ закінчується менш ніж за {hours} год. Не забудьте активувати підписку, щоб не втрачати прогрес!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Ваш демо-доступ закінчився.</b>\n\nДо возобновления демо-периода осталось **{hours} год {minutes} хв.**\n\nАбо ви можете активувати Premium-доступ прямо зараз, натиснувши кнопку 'Оплатити'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Ваш демо-доступ закінчився.</b>\n\nВи можете активувати **ще один** пробний період ({demo_days} дні) або отримати постійний Premium-доступ.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Ваші пробні періоди закінчилися.</b>\n\nДля відновлення доступу, будь ласка, активуйте Premium-підписку. 👇",
        "demo_awaiting_renewal": "Зрозумів. Ваш демо-період відновиться через **{hours} год {minutes} хв.**\n\nВ режимі очікування розсилки відключені, але ви можете активувати Premium у будь-який момент.",
        "pay_info": "💳 Для отримання повного доступу, будь ласка, зв'яжіться з адміністратором.",
        "pay_instructions": "✅ {name}, ласкаво просимо до Premium! Я буду Вашою підтримкою протягом 30 днів. За цей час Ви отримаєте 120 повідомлень (це ~2 грн за повідомлення).\n\nДля активації, будь ласка, перекажіть **245 грн** на цю Банку Monobank:\n\n`https://send.monobank.ua/jar/ao8c487LS`\n\n**ВАЖЛИВО:** Після оплати, будь ласка, надішліть скріншот чека нашому менеджеру: **@fotinia_admin**. Він побачить його та активує ваш доступ вручну.",
        "pay_api_success_test": "✅ {name}, ласкаво просимо до Premium! (Тест API)\nЯ буду Вашою підтримкою протягом 30 днів. За цей час Ви отримаєте 120 повідомлень (це ~2 грн за повідомлення). Натисніть /start.",
        
        # --- ИСПРАВЛЕНИЯ РЕАКЦИЙ И ШАРИНГА (Новые ключи) ---
        "share_text_template": "Подивись, який бот мені допомагає рухатися до мети! @{bot_username}", 
        "reaction_received": "Дякую за твою реакцію, {name}!", 
        "reaction_already_accepted": "{name}, твоя інформація вже прийнята.",
        "share_text_full": "Подивись, яке повідомлення сьогодні надіслав мені мій бот, який допомагає мені бути на позитиві та рухатися до мети!\nСпробуй і ти, це цікаво :-)\n@{bot_username}",
        "share_text_with_quote": "🔥 {quote}\n\nПодивись, яке повідомлення сьогодні надіслав мені мій бот, який допомагає мені бути на позитиві та рухатися до мети!\nСпробуй і ти, це цікаво :-)\n@{bot_username}",

        "profile_title": "👤 <b>Ваш профіль:</b>",
        "profile_name": "📛 Ім'я",
        "profile_challenges_accepted": "⚔️ Прийнято челенджів",
        "profile_challenges_completed": "✅ Виконано",
        "profile_challenge_streak": "🔥 Серія виконань",
        "profile_status": "💰 Статус",
        "profile_likes": "👍 Лайки",
        "profile_dislikes": "👎 Дизлайки",
        "status_premium": "⭐ Premium",
        "status_demo": "🆓 Демо",
        "list_empty": "⚠️ Список для '{title}' порожній.",
        "list_error_format": "⚠️ Помилка форматування тексту для '{title}'. Відсутній ключ: {e}",
        "list_error_index": "⚠️ Сталася помилка під час вибору елемента зі списку '{title}'. Список може бути порожнім.",
        "list_error_unexpected": "⚠️ Сталася непередбачена помилка під час надсилання '{title}'.",
        "list_error_data": "⚠️ Помилка даних для '{title}'. Зверніться до адміністратора.",
        "challenge_already_issued": "⏳ Ви вже отримали челендж на сьогодні.",
        "challenge_pending_acceptance": "🔥 У вас вже є активний челендж. Прийміть його або натисніть 'Новий' у повідомленні вище.",
        "challenge_accepted_msg": "💪 <b>Челендж прийнято:</b>\n\n<i>{challenge_text}</i>",
        "challenge_completed_msg": "✅ Чудово! Челендж виконано!",
        "challenge_completed_edit_err": "⚠️ Не вдалося відредагувати повідомлення про виконання.",
        "challenge_new_day": "⚔️ <b>Челендж дня:</b>\n{challenge_text}",
        "challenge_choose_error": "⚠️ Помилка під час вибору челенджу. Список може бути порожнім.",
        "challenge_button_error": "⚠️ Сталася помилка під час формування кнопок челенджу.",
        "challenge_unexpected_error": "⚠️ Сталася непередбачена помилка під час надсилання челенджу.",
        "challenge_accept_error": "⚠️ Сталася помилка під час прийняття челенджу. Спробуйте запросити челендж знову.",
        "challenge_streak_3_level_1": "🔥🔥🔥 {name}, ти молодець! Виконано 3 челенджі поспіль, і досягнуто 1 рівень. Продовжуй в тому ж темпі, і на тебе чекає нагорода!",
        "unknown_command": "❓ Невідома команда. Будь ласка, використовуйте кнопки.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "Файл users.json ще не створений або порожній.",
        "reload_confirm": "✅ Кеш та завдання планувальника оновлено!",
        "start_required": "Схоже, ми ще не знайомі. Будь ласка, натисніть /start, щоб почати.",
        "admin_new_user": "🎉 Новий користувач: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Показати статистику",
        "admin_bot_started": "🤖 Бот успішно запущен (v10.17 - Refactored)",
        "admin_bot_stopping": "⏳ Бот зупиняється...",
        "lang_choose": "Оберіть мову: 👇",
        "lang_chosen": "✅ Мову встановлено на Українську.",
        
        "btn_motivate": "💪 Мотивуй мене", "btn_rhythm": "🎵 Ритм дня",
        "btn_challenge": "⚔️ Челендж дня", "btn_rules": "📜 Правила Всесвіту",
        "btn_profile": "👤 Профіль",
        "btn_share": "💌 Поділитися з другом",
        "btn_show_users": "📂 Дивитися users.json", "btn_stats": "📊 Статистика",
        "btn_reload_data": "🔄 Оновити",
        "btn_pay_premium": "👑 Хочу Premium",
        "btn_pay_api_test_premium": "👑 Premium (API Тест)",
        "btn_want_demo": "🔄 Хочу демо",
        "btn_challenge_accept": "✅ Прийняти", "btn_challenge_new": "🎲 Новий",
        "btn_challenge_complete": "✅ Виконано",
        
        "btn_settings": "⚙️ Налаштування",
        "btn_back": "↩️ Назад",
        "msg_choose_action": "Оберіть дію:",
        "msg_welcome_back": "🏠 Ви повернулися в головне меню",

        "title_motivation": "💪", "title_rhythm": "🎶 Ритм дня:", "title_rules": "📜 Правила Всесвіту",
        "title_rules_daily": "📜 <b>{title} ({count}/{limit}):</b>",
        "rules_limit_reached": "На сьогодні це всі закони. Нові ти дізнаєшся завтра! 🌙",
        "profile_status_total": "Всього",
        "profile_status_active": "Активних",
        "profile_status_first_time": "Перший раз",
        "profile_status_repeat": "Повторно",
        "profile_status_inactive": "Неактивних",
        "profile_status_demo_expired": "Закінчилося демо",
        "profile_status_blocked": "Заблокували",
    },
    "en": {
        "lang_choose_first": COMMON_LANG_CHOOSE_FIRST,
        "welcome": "🌟 Hello, {name}! I am Fotinia Bot, your personal self-development assistant.\n\nI will send you messages 4 times a day to help you stay focused. You have a trial period ({demo_days} days) to try all features. Let's start! 👇",
        "welcome_return": "🌟 Welcome back, {name}! Glad to see you again. Your {status_text} access is active. Use the buttons below 👇",
        "welcome_renewed_demo": "🌟 {name}, welcome back! You have a new demo period for {demo_days} days. All functions are restored. Previously achieved levels are reset. Good luck! 👇",
        
        "welcome_timezone_note": "\n\nP.S. Your timezone was automatically set to <code>{default_tz}</code>. If this is incorrect, please use the /timezone command to change it.",
        "timezone_command_text": "⚙️ <b>Timezone Settings</b>\n\nYour current timezone: <code>{user_tz}</code>\n\nTo change it, <b>please send your timezone</b> in IANA (TZ Database) format.\n\nExamples:\n<code>Europe/Berlin</code>\n<code>Europe/Warsaw</code>\n<code>America/New_York</code>\n<code>Asia/Tbilisi</code>\n\nSend /cancel to exit.",
        "timezone_set_success": "✅ Timezone updated to <code>{new_tz}</code>.",
        "timezone_set_error": "⚠️ Error. <code>{error_text}</code> is not a valid timezone. Please try again (e.g., <code>Europe/London</code>) or send /cancel.",
        "timezone_cancel": "✅ Setup cancelled. Your timezone remains: <code>{user_tz}</code>.",
        "cmd_cancel": "Cancel",
        "admin_grant_success": "✅ Premium access successfully granted to {name} (ID: {user_id}).",
        "admin_grant_fail_id": "⚠️ Error. User with ID <code>{user_id}</code> not found.",
        "admin_grant_fail_already_paid": "⚠️ User {name} (ID: {user_id}) already has Premium access.",
        "admin_grant_usage": "⚠️ Invalid format. Use: <code>/grant [USER_ID]</code>",
        "user_grant_notification": "🎉 <b>Access Activated!</b>\n\nThe administrator has activated your Premium access. Congratulations!\n\nPlease press /start to refresh your keyboard.",
        
        "demo_expiring_soon_h": "🔒 {name}, your demo access expires in less than {hours} hour(s). Don't forget to activate your subscription to keep your progress!",
        "demo_expired_cooldown": "👋 {name}!\n🔒 <b>Your demo access has expired.</b>\n\nYou can reactivate a new demo period in **{hours}h {minutes}m**.\n\nOr you can activate Premium access right now by pressing 'Pay'. 👇",
        "demo_expired_choice": "👋 {name}!\n🔒 <b>Your demo access has expired.</b>\n\nYou can activate **one more** trial period ({demo_days} days) or get permanent Premium access.",
        "demo_expired_final": "👋 {name}!\n🔒 <b>Your trial periods have ended.</b>\n\nTo resume access, please activate your Premium subscription. 👇",
        "demo_awaiting_renewal": "Got it. Your demo period will resume in **{hours}h {minutes}m**.\n\nBroadcasts are disabled in standby mode, but you can activate Premium at any time.",
        "pay_info": "💳 For full access, please contact the administrator.",
        "pay_instructions": "✅ {name}, welcome to Premium! I will be your support for 30 days. During this time, you will receive 120 messages (that's ~2 UAH per message). Press /start.",
        "pay_api_success_test": "✅ {name}, welcome to Premium! (API Test)\nI will be your support for 30 days. During this time, you will receive 120 messages (that's ~2 UAH per message). Press /start.",
        
        # --- ИСПРАВЛЕНИЯ РЕАКЦИЙ И ШАРИНГА (Новые ключи) ---
        "share_text_template": "Check out this bot that's helping me reach my goals! @{bot_username}", 
        "reaction_received": "Thank you for your reaction, {name}!", 
        "reaction_already_accepted": "{name}, your information has already been received.",
        "share_text_full": "Look what message my bot sent me today, which helps me stay positive and move towards my goal!\nTry it yourself, it's interesting :-)\n@{bot_username}",
        "share_text_with_quote": "🔥 {quote}\n\nLook what message my bot sent me today, which helps me stay positive and move towards my goal!\nTry it yourself, it's interesting :-)\n@{bot_username}",

        "profile_title": "👤 <b>Your Profile:</b>",
        "profile_name": "📛 Name",
        "profile_challenges_accepted": "⚔️ Challenges Accepted",
        "profile_challenges_completed": "✅ Completed",
        "profile_challenge_streak": "🔥 Completion Streak",
        "profile_status": "💰 Status",
        "profile_likes": "👍 Likes",
        "profile_dislikes": "👎 Dislikes",
        "status_premium": "⭐ Premium",
        "status_demo": "🆓 Demo",
        "list_empty": "⚠️ The list for '{title}' is empty.",
        "list_error_format": "⚠️ Error formatting text for '{title}'. Missing key: {e}",
        "list_error_index": "⚠️ An error occurred while selecting an item from the list '{title}'. The list may be empty.",
        "list_error_unexpected": "⚠️ An unexpected error occurred while sending '{title}'.",
        "list_error_data": "⚠️ Data error for '{title}'. Please contact the administrator.",
        "challenge_already_issued": "⏳ You have already received a challenge for today.",
        "challenge_pending_acceptance": "🔥 You already have an active challenge. Accept it or press 'New' in the message above.",
        "challenge_accepted_msg": "💪 <b>Challenge accepted:</b>\n\n<i>{challenge_text}</i>",
        "challenge_completed_msg": "✅ Excellent! Challenge completed!",
        "challenge_completed_edit_err": "⚠️ Failed to edit the completion message.",
        "challenge_new_day": "⚔️ <b>Challenge of the day:</b>\n{challenge_text}",
        "challenge_choose_error": "⚠️ Error choosing challenge. The list may be empty.",
        "challenge_button_error": "⚠️ An error occurred while generating challenge buttons.",
        "challenge_unexpected_error": "⚠️ An unexpected error occurred while sending the challenge.",
        "challenge_accept_error": "⚠️ An error occurred while accepting the challenge. Please request a new challenge.",
        "challenge_streak_3_level_1": "🔥🔥🔥 {name}, you're amazing! 3 challenges completed in a row, and Level 1 achieved. Keep up the pace, and a reward awaits you!",
        "unknown_command": "❓ Unknown command. Please use the buttons.",
        "users_file_caption": "📂 users.json",
        "users_file_empty": "The users.json file has not been created or is empty.",
        "reload_confirm": "✅ Cache and scheduler tasks have been updated!",
        "start_required": "It seems we haven't met. Please press /start to begin.",
        "admin_new_user": "🎉 New user: {name} (ID: {user_id})",
        "admin_stats_button": "📊 Show Statistics",
        "admin_bot_started": "🤖 Bot successfully launched (v10.17 - Refactored)",
        "admin_bot_stopping": "⏳ Bot is stopping...",
        "lang_choose": "Select language: 👇",
        "lang_chosen": "✅ Language set to English.",
        
        "btn_motivate": "💪 Motivate me", "btn_rhythm": "🎵 Rhythm of the Day",
        "btn_challenge": "⚔️ Challenge of the Day", "btn_rules": "📜 Rules of the Universe",
        "btn_profile": "👤 Profile",
        "btn_share": "💌 Share",
        "btn_show_users": "📂 View users.json", "btn_stats": "📊 Statistics",
        "btn_reload_data": "🔄 Reload",
        "btn_pay_premium": "👑 Want Premium",
        "btn_pay_api_test_premium": "👑 Premium (API Test)",
        "btn_want_demo": "🔄 Want Demo",
        "btn_challenge_accept": "✅ Accept", "btn_challenge_new": "🎲 New",
        "btn_challenge_complete": "✅ Done",

        "btn_settings": "⚙️ Settings",
        "btn_back": "↩️ Back",
        "msg_choose_action": "Choose an action:",
        "msg_welcome_back": "🏠 You are back in the main menu",

        "title_motivation": "💪", "title_rhythm": "🎶 Rhythm of theDay:", "title_rules": "📜 Rules of the Universe",
        "title_rules_daily": "📜 <b>{title} ({count}/{limit}):</b>",
        "rules_limit_reached": "That's all the laws for today. You will learn new ones tomorrow! 🌙",
        "profile_status_total": "Total",
        "profile_status_active": "Active",
        "profile_status_first_time": "First time",
        "profile_status_repeat": "Repeat",
        "profile_status_inactive": "Inactive",
        "profile_status_demo_expired": "Demo expired",
        "profile_status_blocked": "Blocked",
    }
}


def t(key: str, lang: Lang = DEFAULT_LANG, **kwargs) -> str:
    """
    Главная функция для получения перевода.
    t('welcome', 'ua', name="Олег")
    """
    # 1. Пытаемся взять перевод на нужном языке
    # 2. Если его нет, пытаемся взять на языке по умолчанию (ru)
    # 3. Если и его нет, возвращаем сам ключ (например, 'btn_settings')
    text = translations.get(lang, translations[DEFAULT_LANG]).get(key, key)
    
    try:
        # Добавляем {name} по умолчанию, чтобы избежать KeyError
        if 'name' not in kwargs and '{name}' in text:
            kwargs['name'] = 'друг'
            
        return text.format(**kwargs)
    except KeyError as e:
        # Если не хватает какого-то другого ключа (напр. {demo_days})
        logger.error(f"Missing key '{e}' during formatting text for key '{key}' in lang '{lang}'")
        return text.replace(f"{{{str(e)}}}", "[ДАННЫЕ]") # Возвращаем текст без сломанного ключа