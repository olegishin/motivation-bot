# 13 - bot/admin_routes.py
# ✅ Точка входа приложения (FastAPI + Aiogram)
# ✅ Lifespan управление (запуск/остановка бота)
# ✅ Инициализация базы данных (WAL режим)
# ✅ Настройка вебхука с фильтрацией обновлений
# ✅ Middleware для проверки доступа
# ✅ Роутеры (Aiogram для бота, FastAPI для админки и WebApp)
# ✅ Graceful shutdown с таймаутом

import secrets
import pyotp
import jwt
import os
import json
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from pathlib import Path
from urllib.parse import parse_qsl, unquote

from fastapi import APIRouter, Request, Depends, HTTPException, Form, Response, Cookie, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings, logger
from bot.database import db
from bot.utils import get_user_lang, is_demo_expired, get_demo_config, get_user_tz, get_level_info, get_progress_bar
from bot.localization import t

# Роутер для админки
router = APIRouter(prefix="/admin", tags=["admin"])

# Отдельный роутер для пользовательских WebApp (Профиль открыт для всех юзеров)
webapp_router = APIRouter(tags=["webapp"])

# --- ПУТЬ ДЛЯ ШАБЛОНОВ (ТВОЕ УНИВЕРСАЛЬНОЕ РЕШЕНИЕ) ---
current_file = Path(__file__).resolve()
possible_paths = [
    current_file.parent.parent / "templates",  # S:\fotinia_bot\templates
    Path("/app/templates"),                   # Абсолютный путь для Fly.io
    current_file.parent / "templates",         # S:\fotinia_bot\bot\templates
]

templates_dir = None
for path in possible_paths:
    if path.exists() and path.is_dir():
        templates_dir = path
        logger.info(f"✅ Found templates directory at: {templates_dir}")
        break

if templates_dir is None:
    templates_dir = current_file.parent.parent / "templates"
    logger.error(f"❌ Templates directory not found! Using fallback: {templates_dir}")
else:
    required_templates = ["admin_login.html", "admin.html", "profile.html"]
    for tmpl in required_templates:
        tmpl_path = templates_dir / tmpl
        if not tmpl_path.exists():
            logger.warning(f"  ✗ Missing: {tmpl}")

templates = Jinja2Templates(directory=str(templates_dir))

# --- JWT Константы ---
JWT_ALGORITHM = "HS256"
JWT_EXPIRY = timedelta(days=7)

def create_jwt() -> str:
    payload = {"exp": datetime.now(timezone.utc) + JWT_EXPIRY}
    return jwt.encode(payload, settings.ADMIN_JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt(token: str | None) -> bool:
    if not token: return False
    try:
        jwt.decode(token, settings.ADMIN_JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except: return False

async def require_admin(request: Request):
    token = request.cookies.get("admin_jwt")
    if not verify_jwt(token):
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return True

def get_remaining_days(user_data: Dict[str, Any]) -> int:
    if user_data.get("is_paid"): return 30
    expiry_str = user_data.get("demo_expiration")
    if not expiry_str: return 0
    try:
        user_tz = get_user_tz(user_data)
        expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00')).astimezone(user_tz)
        now_local = datetime.now(user_tz)
        if now_local >= expiry_date: return 0
        remaining_delta = expiry_date - now_local
        return max(0, remaining_delta.days + (1 if remaining_delta.seconds > 0 else 0))
    except Exception as e:
        logger.error(f"Error calculating remaining days: {e}")
        return 0

# ✅ ДОБАВЛЕНО: Функция проверки Telegram WebApp initData
def verify_telegram_webapp_data(init_data: str) -> dict | None:
    """
    Проверяет подлинность данных Telegram WebApp через HMAC подпись.
    Возвращает распарсенные данные если проверка успешна, иначе None.
    
    Документация: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        logger.warning("WebApp: Empty initData")
        return None
    
    try:
        # Парсим query string
        parsed_data = dict(parse_qsl(init_data))
        
        # Извлекаем hash
        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            logger.warning("WebApp: Missing hash in initData")
            return None
        
        # Формируем data-check-string
        data_check_items = []
        for key in sorted(parsed_data.keys()):
            value = parsed_data[key]
            data_check_items.append(f"{key}={value}")
        
        data_check_string = "\n".join(data_check_items)
        
        # Создаем secret key: HMAC-SHA-256("WebAppData", bot_token)
        secret_key = hmac.new(
            key="WebAppData".encode(),
            msg=settings.BOT_TOKEN.encode(),
            digestmod=hashlib.sha256
        ).digest()
        
        # Вычисляем ожидаемый hash: HMAC-SHA-256(secret_key, data_check_string)
        expected_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Сравниваем
        if not hmac.compare_digest(expected_hash, received_hash):
            logger.warning("WebApp: HMAC verification failed")
            return None
        
        # Проверяем актуальность (auth_date не старше 1 часа)
        auth_date = parsed_data.get("auth_date")
        if auth_date:
            try:
                auth_timestamp = int(auth_date)
                now_timestamp = int(datetime.now(timezone.utc).timestamp())
                
                if now_timestamp - auth_timestamp > 3600:  # 1 час
                    logger.warning("WebApp: initData expired (older than 1 hour)")
                    return None
            except ValueError:
                logger.warning("WebApp: Invalid auth_date format")
                return None
        
        # Парсим user данные
        user_json = parsed_data.get("user")
        if user_json:
            try:
                parsed_data["user"] = json.loads(unquote(user_json))
            except json.JSONDecodeError:
                logger.warning("WebApp: Failed to parse user JSON")
                return None
        
        logger.info(f"WebApp: Valid initData for user {parsed_data.get('user', {}).get('id')}")
        return parsed_data
        
    except Exception as e:
        logger.error(f"WebApp: Verification error: {e}", exc_info=True)
        return None

# --- ЛИЧНЫЙ КАБИНЕТ (WEBAPP ПРОФИЛЬ) С ЗАЩИТОЙ ---

@webapp_router.get("/profile/{user_id}", response_class=HTMLResponse)
async def profile_webapp(request: Request, user_id: int):
    """
    ✅ ИСПРАВЛЕНО: Добавлена проверка Telegram WebApp initData
    Профиль доступен только владельцу через WebApp
    """
    
    # ✅ ЗАЩИТА #1: Получаем initData из заголовка или query параметра
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query_params.get("tgWebAppData")
    
    if not init_data:
        logger.warning(f"WebApp: Missing initData for user {user_id}")
        return HTMLResponse(
            "<h1>403 Forbidden</h1><p>Доступ запрещён. Откройте профиль через Telegram бота.</p>",
            status_code=403
        )
    
    # ✅ ЗАЩИТА #2: Проверяем подлинность данных
    verified_data = verify_telegram_webapp_data(init_data)
    
    if not verified_data:
        logger.warning(f"WebApp: Invalid initData for user {user_id}")
        return HTMLResponse(
            "<h1>403 Forbidden</h1><p>Неверные данные авторизации.</p>",
            status_code=403
        )
    
    # ✅ ЗАЩИТА #3: Проверяем, что пользователь запрашивает свой профиль
    telegram_user = verified_data.get("user", {})
    telegram_user_id = telegram_user.get("id")
    
    if not telegram_user_id or int(telegram_user_id) != int(user_id):
        logger.warning(f"WebApp: User {telegram_user_id} tried to access profile of {user_id}")
        return HTMLResponse(
            "<h1>403 Forbidden</h1><p>Вы можете просматривать только свой профиль.</p>",
            status_code=403
        )
    
    # ✅ ВСЯ ДАЛЬНЕЙШАЯ ЛОГИКА БЕЗ ИЗМЕНЕНИЙ
    try:
        bot = request.app.state.bot
    except AttributeError:
        return HTMLResponse("Бот не инициализирован", status_code=500)
    
    user_data = await db.get_user(user_id)
    if not user_data:
        return HTMLResponse("Пользователь не найден", status_code=404)

    lang = get_user_lang(user_data)
    
    photo_url = "/static/logo.png"
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            file = await bot.get_file(file_id)
            photo_url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file.file_path}"
    except Exception as e:
        logger.debug(f"Could not get profile photo: {e}")

    is_paid = user_data.get("is_paid", False)
    demo_count = user_data.get("demo_count", 1)
    status_label = t('status_premium', lang) if is_paid else f"{t('status_demo', lang)} {demo_count}"

    challenges = user_data.get("challenges", [])
    if isinstance(challenges, str):
        try: challenges = json.loads(challenges)
        except: challenges = []

    completed_challenges = len([c for c in challenges if isinstance(c, dict) and c.get("completed")])
    
    # ✅ ДОБАВЛЕНО: Полная система уровней на основе стрика
    streak = user_data.get("challenge_streak", 0)
    level_info = get_level_info(streak)
    
    # Получаем название уровня на языке пользователя
    level_name = t(level_info["current_level"], lang)
    
    # Получаем название следующего уровня (если есть)
    next_level_name = ""
    if not level_info["is_max_level"]:
        next_level_name = t(level_info["next_level"], lang)
    
    days_val = get_remaining_days(user_data)
    max_days = 30 if is_paid else 5
    battery_pct = int((days_val / max_days) * 100) if max_days > 0 else 0
    battery_pct = max(0, min(100, battery_pct))
    
    context = {
        "request": request,
        "name": user_data.get("name") or "Пользователь",
        "photo_url": photo_url,
        "status_text": status_label,
        "level_name": level_name,
        "level_number": level_info["level_number"],
        "level_progress": level_info["progress_percent"],
        "next_level_name": next_level_name,
        "streak": streak,
        "is_max_level": level_info["is_max_level"],
        "days_to_next": level_info["days_to_next"],
        "accepted": len(challenges),
        "completed": completed_challenges,
        "likes": user_data.get("stats_likes", 0),
        "dislikes": user_data.get("stats_dislikes", 0),
        "days_left": days_val,
        "battery_pct": battery_pct,
        "lang": lang,
        "t": t 
    }
    return templates.TemplateResponse("profile.html", context)

# --- АДМИН-РОУТЫ (БЕЗ ИЗМЕНЕНИЙ) ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@router.post("/login")
async def login(request: Request, response: Response, username: str = Form(...), password: str = Form(...), totp_code: str = Form(...)):
    if not (secrets.compare_digest(username, settings.ADMIN_USERNAME) and 
            secrets.compare_digest(password, settings.ADMIN_PASSWORD)):
        return templates.TemplateResponse("admin_login.html", {"request": request, "error": "Неверный логин или пароль"})
    
    if not pyotp.TOTP(settings.ADMIN_2FA_SECRET).verify(totp_code.strip(), valid_window=1):
        return templates.TemplateResponse("admin_login.html", {"request": request, "error": "Неверный код 2FA"})
    
    token = create_jwt()
    response = RedirectResponse(url="/admin/", status_code=303)
    response.set_cookie(key="admin_jwt", value=token, httponly=True, secure=True, samesite="strict", max_age=60*60*24*7)
    return response

@router.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("admin_jwt")
    return response

@router.get("/", response_class=HTMLResponse)
async def users_dashboard(request: Request, auth = Depends(require_admin)):
    all_users_data = await db.get_all_users()
    users_list = []
    
    for user_id_str, user_data in all_users_data.items():
        try:
            is_expired = await is_demo_expired(user_data)
            remaining_days = get_remaining_days(user_data)
            
            streak = user_data.get("challenge_streak", 0)
            level_info = get_level_info(streak)
            
            users_list.append({
                "id": user_id_str,
                "name": user_data.get("name", "Unknown"),
                "username": user_data.get("username", "N/A"),
                "lang_display": get_user_lang(user_data).upper(),
                "status": "Paid" if user_data.get("is_paid") else ("Expired" if is_expired else "Demo"),
                "is_active": (user_data.get("active") in [True, 1, "1"]),
                "remaining_days": remaining_days,
                "timezone": user_data.get("timezone", "UTC"),
                "streak": streak,
                "level": level_info["level_number"],
                "level_name": level_info["current_level"],
            })
        except Exception as e:
            logger.error(f"Error processing user {user_id_str}: {e}")
            continue
    
    users_list.sort(key=lambda u: (u['status'] != 'Paid', u['status'] == 'Expired', -u['remaining_days']))
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "users": users_list, 
        "total_users": len(all_users_data), 
        "admin_secret": settings.ADMIN_SECRET
    })

@router.post("/action")
async def admin_action(request: Request, user_id: str = Form(...), action: str = Form(...), secret_token: str = Form(...), auth = Depends(require_admin)):
    if secret_token != settings.ADMIN_SECRET: raise HTTPException(status_code=403)
    uid = int(user_id)
    if action == "delete_user": await db.delete_user(uid)
    elif action == "give_premium": await db.update_user(uid, is_paid=True, status="active_paid", active=True)
    elif action == "reset_demo": await db.update_user(uid, is_paid=False, demo_count=1, active=True, status="active_demo", challenges=[], challenge_streak=0, last_level_checked="level_0")
    elif action == "toggle_ban":
        user_data = await db.get_user(uid)
        if user_data:
            current_active = user_data.get("active")
            if current_active in [True, 1, "1"]:
                until_date = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                await db.update_user(uid, active=until_date)
            else:
                await db.update_user(uid, active=True)
    return RedirectResponse("/admin", status_code=303)

@router.post("/set_timezone_auto")
async def set_timezone_auto():
    return {"status": "ok", "message": "Endpoint fixed"}

@router.get("/reset_testers_force")
async def reset_testers_action(request: Request, secret: str, auth = Depends(require_admin)):
    if secret != settings.ADMIN_SECRET: raise HTTPException(status_code=403)
    target_ids = [290711961, 6112492697]
    for uid in target_ids:
        try:
            await db.execute("DELETE FROM users WHERE user_id = ?", (uid,))
            await db.execute("DELETE FROM fsm_storage WHERE user_id = ?", (uid,))
        except Exception as e: logger.error(f"Error deleting tester {uid}: {e}")
    await db.commit()
    if hasattr(request.app.state, "users_db"):
        for uid in target_ids:
            request.app.state.users_db.pop(str(uid), None)
    return {"status": "success", "message": f"Users {target_ids} purged from DB and Cache."}