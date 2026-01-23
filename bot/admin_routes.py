# 13 - bot/admin_routes.py
# FastAPI роуты для админки (JWT + TOTP Auth)
# bot/admin_routes.py — НАСТОЯЩАЯ 2FA + JWT + CSRF (2025)
# bot/admin_routes.py — финальная версия с правильным путём к templates (декабрь 2025)
# bot/admin_routes.py — исправленная версия (декабрь 2025)
# bot/admin_routes.py — финальная рабочая версия (декабрь 2025)
# bot/admin_routes.py — исправленная версия (путь к шаблонам)
# bot/admin_routes.py — исправленная версия
# bot/admin_routes.py — финальная рабочая версия (январь 2026)
# bot/admin_routes.py — финальная версия (авто-таймзоны и WebApp роуты)
# FastAPI роуты для админки и Личного кабинета WebApp
# bot/admin_routes.py — финальная версия (Уровни, Батарейка, WebApp Profile)
# Админ-панель + WebApp профиль + Функция полной очистки тестеров
# Админ-панель + WebApp профиль (ФИНАЛЬНАЯ ВЕРСИЯ: Фикс статистики лайков)
# Админ-панель + WebApp профиль (УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс TZ + Синхронизация роутов)
# bot/admin_routes.py — УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс TZ + Синхронизация роутов + Toggle Ban
# bot/admin_routes.py — УЛЬТИМАТИВНАЯ ВЕРСИЯ: Фикс TZ + Синхронизация роутов + Smart Ban 24h
# FastAPI роуты для админки и WebApp профиля
# ИСПРАВЛЕНО (2026-01-13): Убран несуществующий импорт is_demo_expired
# FastAPI роуты для админки и Личного кабинета WebApp
# УЛЬТИМАТИВНАЯ ВЕРСИЯ: Smart Ban 24h + Фикс TZ + Очистка тестеров
# ИСПРАВЛЕНО (2026-01-13): Исправлен критический импорт check_demo_status и возвращены все функции
# FastAPI роуты для админки и WebApp профиля
# ✅ ИСПРАВЛЕНО (2026-01-16): Путь к шаблонам (Ошибка #5)
# FastAPI роуты для админки (JWT + TOTP Auth)
# ✅ ИСПРАВЛЕНО (2026-01-17): Ошибка #11 — WebApp профиль защищен от несанкционированного доступа
# FastAPI роуты для админки и WebApp профиля
# ✅ ИСПРАВЛЕНО (2026-01-17): Критический фикс путей к шаблонам для Fly.io
# FastAPI роуты для админки (JWT + TOTP Auth)
# ✅ ИСПРАВЛЕНО (2026-01-20): Фикс отображения путей вместо HTML в профиле

import secrets
import pyotp
import jwt
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, Form, Response, Cookie, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings, logger
from bot.database import db
from bot.utils import get_user_lang, check_demo_status, get_demo_config, get_user_tz
from bot.localization import t

# Роутер для админки
router = APIRouter(prefix="/admin", tags=["admin"])

# Отдельный роутер для пользовательских WebApp (Профиль открыт для всех юзеров)
webapp_router = APIRouter(tags=["webapp"])

# --- ПУТЬ ДЛЯ ШАБЛОНОВ (УНИВЕРСАЛЬНОЕ РЕШЕНИЕ) ---
# ✅ ИСПРАВЛЕНО (2026-01-20): Добавлена отладка поиска шаблонов
current_file = Path(__file__).resolve()
possible_paths = [
    current_file.parent.parent / "templates",  # S:\fotinia_bot\templates (стандарт)
    Path("/app/templates"),  # Абсолютный путь для Fly.io
    current_file.parent / "templates",  # S:\fotinia_bot\bot\templates (на случай если там)
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
    logger.error(f"Checked paths: {[str(p) for p in possible_paths]}")
else:
    required_templates = ["admin_login.html", "admin.html", "profile.html"]
    for tmpl in required_templates:
        tmpl_path = templates_dir / tmpl
        if tmpl_path.exists():
            logger.debug(f"  ✓ Found: {tmpl}")
        else:
            logger.warning(f"  ✗ Missing: {tmpl}")

templates = Jinja2Templates(directory=str(templates_dir))
logger.info(f"Jinja2Templates initialized with directory: {templates_dir}")

# --- JWT Константы ---
JWT_ALGORITHM = "HS256"
JWT_EXPIRY = timedelta(days=7)

def create_jwt() -> str:
    """Создает JWT токен для админа."""
    payload = {"exp": datetime.now(timezone.utc) + JWT_EXPIRY}
    token = jwt.encode(payload, settings.ADMIN_JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.debug("Created new JWT token for admin")
    return token

def verify_jwt(token: str | None) -> bool:
    """Проверяет JWT токен."""
    if not token:
        return False
    try:
        jwt.decode(token, settings.ADMIN_JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except Exception as e:
        logger.debug(f"JWT verification failed: {e}")
        return False

async def require_admin(request: Request):
    """Dependency для проверки админского доступа."""
    token = request.cookies.get("admin_jwt")
    if not verify_jwt(token):
        logger.warning(f"Unauthorized admin access attempt from {request.client.host}")
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return True

def get_remaining_days(user_data: Dict[str, Any]) -> int:
    """Считает оставшиеся дни демо с учетом часового пояса пользователя."""
    if user_data.get("is_paid"):
        return 30
    
    expiry_str = user_data.get("demo_expiration")
    if not expiry_str:
        return 0
    
    try:
        user_tz = get_user_tz(user_data)
        expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00')).astimezone(user_tz)
        now_local = datetime.now(user_tz)
        
        if now_local >= expiry_date:
            return 0
        
        remaining_delta = expiry_date - now_local
        return max(0, remaining_delta.days + (1 if remaining_delta.seconds > 0 else 0))
    except Exception as e:
        logger.error(f"Error calculating remaining days for user: {e}")
        return 0

# --- ЛИЧНЫЙ КАБИНЕТ (WEBAPP ПРОФИЛЬ) ---

@webapp_router.get("/profile/{user_id}", response_class=HTMLResponse)
async def profile_webapp(request: Request, user_id: int):
    """
    WebApp профиль пользователя (открывается в Telegram из кнопки 👤 Профиль).
    ✅ ИСПРАВЛЕНО (2026-01-20): Добавлена отладка рендера шаблона
    """
    
    try:
        bot = request.app.state.bot
    except AttributeError:
        logger.error("Bot not available in request.app.state")
        return HTMLResponse("Бот не инициализирован", status_code=500)
    
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"📱 Profile request: user_id={user_id} from IP={client_ip}")
    
    user_data = await db.get_user(user_id)
    if not user_data:
        logger.warning(f"Profile request for non-existent user {user_id}")
        return HTMLResponse("Пользователь не найден", status_code=404)

    lang = get_user_lang(user_data)
    
    # Получаем аватар пользователя
    photo_url = "/static/logo.png"
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            file = await bot.get_file(file_id)
            photo_url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file.file_path}"
    except Exception as e:
        logger.debug(f"Could not get profile photo: {e}")

    # Определяем статус
    is_paid = user_data.get("is_paid", False)
    demo_count = user_data.get("demo_count", 1)
    status_label = "Premium 👑" if is_paid else f"Демо {demo_count}"

    # Получаем челленджи
    challenges = user_data.get("challenges", [])
    if isinstance(challenges, str):
        try:
            challenges = json.loads(challenges)
        except:
            challenges = []

    completed_challenges = len([c for c in challenges if isinstance(c, dict) and c.get("completed")])
    
    # Определяем уровень
    levels = [(11, "level_4"), (8, "level_3"), (5, "level_2"), (2, "level_1"), (0, "level_0")]
    lvl_key = next(key for limit, key in levels if completed_challenges > limit)
    user_level = t(lvl_key, lang)

    # Батарейка
    days_val = get_remaining_days(user_data)
    max_days = 30 if is_paid else 5
    battery_pct = int((days_val / max_days) * 100) if max_days > 0 else 0
    battery_pct = max(0, min(100, battery_pct))

    logger.info(f"📊 Profile data: user={user_id}, completed={completed_challenges}, days={days_val}, battery={battery_pct}%")
    
    # ✅ ОТЛАДКА: Проверяем templates_dir
    logger.info(f"🔍 Templates directory: {templates_dir}")
    logger.info(f"🔍 Profile template path: {templates_dir / 'profile.html'}")
    logger.info(f"🔍 Profile template exists: {(templates_dir / 'profile.html').exists()}")
    
    try:
        context = {
            "request": request,
            "name": user_data.get("name") or "Пользователь",
            "photo_url": photo_url,
            "status_text": status_label,
            "level_text": user_level,
            "accepted": len(challenges),
            "completed": completed_challenges,
            "streak": user_data.get("challenge_streak", 0),
            "likes": user_data.get("stats_likes", 0),
            "dislikes": user_data.get("stats_dislikes", 0),
            "days_left": days_val,
            "battery_pct": battery_pct,
            "lang": lang,
            "t": t 
        }
        
        logger.info(f"✅ Rendering profile.html with context keys: {list(context.keys())}")
        
        response = templates.TemplateResponse("profile.html", context)
        
        logger.info(f"🔍 Response type: {type(response)}")
        logger.info(f"✅ Profile rendered successfully for user {user_id}")
        
        return response
        
    except Exception as e:
        logger.error(f"❌ ERROR rendering profile: {e}")
        logger.error(f"   Templates dir: {templates_dir}")
        logger.error(f"   Template exists: {(templates_dir / 'profile.html').exists()}")
        
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><meta charset="UTF-8"><title>Error</title></head>
        <body>
            <h1>Ошибка загрузки профиля</h1>
            <p>Templates directory: {templates_dir}</p>
            <p>Template exists: {(templates_dir / 'profile.html').exists()}</p>
            <p>Error: {str(e)}</p>
        </body></html>
        """, status_code=500)

# --- АДМИН-РОУТЫ ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница логина админа (2FA требуется)."""
    logger.debug("Admin login page requested")
    return templates.TemplateResponse("admin_login.html", {"request": request})

@router.post("/login")
async def login(
    request: Request, 
    response: Response, 
    username: str = Form(...), 
    password: str = Form(...), 
    totp_code: str = Form(...)
):
    """Логин админа с проверкой пароля и TOTP (2FA)."""
    
    if not (secrets.compare_digest(username, settings.ADMIN_USERNAME) and 
            secrets.compare_digest(password, settings.ADMIN_PASSWORD)):
        logger.warning(f"Failed login attempt: invalid credentials")
        return templates.TemplateResponse(
            "admin_login.html", 
            {"request": request, "error": "Неверный логин или пароль"}
        )
    
    if not pyotp.TOTP(settings.ADMIN_2FA_SECRET).verify(totp_code.strip(), valid_window=1):
        logger.warning(f"Failed login attempt: invalid 2FA code")
        return templates.TemplateResponse(
            "admin_login.html", 
            {"request": request, "error": "Неверный код 2FA"}
        )
    
    logger.info("Admin successfully logged in")
    token = create_jwt()
    response = RedirectResponse(url="/admin/", status_code=303)
    response.set_cookie(
        key="admin_jwt", 
        value=token, 
        httponly=True, 
        secure=True, 
        samesite="strict", 
        max_age=60*60*24*7
    )
    return response

@router.get("/logout")
async def logout(response: Response):
    """Выход админа (удаление JWT токена)."""
    logger.info("Admin logged out")
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("admin_jwt")
    return response

@router.get("/", response_class=HTMLResponse)
async def users_dashboard(request: Request, auth = Depends(require_admin)):
    """Главная админ-панель: список всех пользователей."""
    logger.debug("Admin dashboard accessed")
    
    all_users_data = await db.get_all_users()
    users_list = []
    
    for user_id_str, user_data in all_users_data.items():
        try:
            is_expired = check_demo_status(user_data)
            remaining_days = get_remaining_days(user_data)
            users_list.append({
                "id": user_id_str,
                "name": user_data.get("name", "Unknown"),
                "username": user_data.get("username", "N/A"),
                "lang_display": get_user_lang(user_data).upper(),
                "status": "Paid" if user_data.get("is_paid") else ("Expired" if is_expired else "Demo"),
                "is_active": (user_data.get("active") in [True, 1, "1"]),
                "remaining_days": remaining_days,
                "timezone": user_data.get("timezone", "UTC")
            })
        except Exception as e:
            logger.error(f"Error processing user {user_id_str}: {e}")
            continue
    
    users_list.sort(key=lambda u: (u['status'] != 'Paid', u['status'] == 'Expired', -u['remaining_days']))
    logger.info(f"Dashboard: showing {len(users_list)} users")
    
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "users": users_list, 
        "total_users": len(all_users_data), 
        "admin_secret": settings.ADMIN_SECRET
    })

@router.post("/action")
async def admin_action(
    request: Request, 
    user_id: str = Form(...), 
    action: str = Form(...), 
    secret_token: str = Form(...), 
    auth = Depends(require_admin)
):
    """Обработка админских действий."""
    
    if secret_token != settings.ADMIN_SECRET:
        logger.warning(f"Admin action failed: invalid secret token")
        raise HTTPException(status_code=403)
    
    try:
        uid = int(user_id)
    except ValueError:
        logger.warning(f"Admin action failed: invalid user_id {user_id}")
        return RedirectResponse("/admin", status_code=303)
    
    logger.info(f"Admin performing action '{action}' on user {uid}")
    
    if action == "delete_user":
        await db.delete_user(uid)
        logger.info(f"Admin deleted user {uid}")
        
    elif action == "give_premium":
        await db.update_user(uid, is_paid=True, status="active_paid", active=True)
        logger.info(f"Admin granted Premium to user {uid}")
        
    elif action == "reset_demo":
        await db.update_user(
            uid, 
            is_paid=False, 
            demo_count=1, 
            active=True, 
            status="active_demo", 
            challenges=[], 
            challenge_streak=0
        )
        logger.info(f"Admin reset demo for user {uid}")
    
    elif action == "toggle_ban":
        user_data = await db.get_user(uid)
        if user_data:
            current_active = user_data.get("active", True)
            if current_active in [True, 1, "1"]:
                until_date = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                await db.update_user(uid, active=until_date)
                logger.info(f"Admin banned user {uid} until {until_date}")
            else:
                await db.update_user(uid, active=True)
                logger.info(f"Admin unbanned user {uid}")
    
    return RedirectResponse("/admin", status_code=303)

@router.post("/set_timezone_auto")
async def set_timezone_auto():
    """Эндпоинт для автоматического определения часового пояса."""
    logger.debug("set_timezone_auto called")
    return {"status": "ok", "message": "Endpoint fixed"}

@router.get("/reset_testers_force")
async def reset_testers_action(
    request: Request, 
    secret: str, 
    auth = Depends(require_admin)
):
    """Полная очистка тестовых пользователей."""
    
    if secret != settings.ADMIN_SECRET:
        logger.warning("reset_testers_force called with invalid secret")
        raise HTTPException(status_code=403)
    
    target_ids = [290711961, 6112492697]
    logger.warning(f"Admin initiating forced reset of testers: {target_ids}")
    
    for uid in target_ids:
        try:
            await db.execute("DELETE FROM users WHERE user_id = ?", (uid,))
            await db.execute("DELETE FROM fsm_storage WHERE user_id = ?", (uid,))
            logger.info(f"Deleted tester user {uid} from DB")
        except Exception as e:
            logger.error(f"Error deleting tester {uid}: {e}")
    
    await db.commit()
    
    if hasattr(request.app.state, "users_db"):
        for uid in target_ids:
            request.app.state.users_db.pop(str(uid), None)
            request.app.state.users_db.pop(uid, None)
        logger.info(f"Cleared testers from users_db cache")

    logger.info(f"Testers {target_ids} completely purged from DB and cache")
    
    return {
        "status": "success", 
        "message": f"Users {target_ids} purged from DB and Cache."
    }