import secrets
import pyotp
import jwt
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException, Form, Response, Cookie, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings, logger
from bot.database import db
from bot.utils import get_user_lang, is_demo_expired, get_demo_config
from bot.localization import t

# Роутер для админки
router = APIRouter(prefix="/admin", tags=["admin"])

# Отдельный роутер для пользовательских WebApp (Профиль открыт для всех юзеров)
webapp_router = APIRouter(tags=["webapp"])

# --- ЖЕСТКИЙ ПУТЬ ДЛЯ DOCKER (FLY.IO) ---
templates = Jinja2Templates(directory="/app/bot/templates")

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
    if user_data.get("is_paid"): return 30  # Визуально для Premium
    expiry_str = user_data.get("demo_expiration")
    if not expiry_str: return 0
    try:
        # Убираем возможные лишние символы и приводим к UTC
        expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
            
        now_utc = datetime.now(timezone.utc)
        if now_utc >= expiry_date: return 0
        
        remaining_delta = expiry_date - now_utc
        return max(0, remaining_delta.days)
    except Exception as e:
        logger.error(f"Error calculating remaining days: {e}")
        return 0

# --- ЛИЧНЫЙ КАБИНЕТ (WEBAPP ПРОФИЛЬ) ---
@webapp_router.get("/profile/{user_id}", response_class=HTMLResponse)
async def profile_webapp(request: Request, user_id: int):
    # Получаем бота из app.state, чтобы избежать циклического импорта
    bot = request.app.state.bot 
    
    user_data = await db.get_user(user_id)
    if not user_data:
        return HTMLResponse("Пользователь не найден", status_code=404)

    lang = get_user_lang(user_data)
    
    # --- 1. Фото пользователя (из Telegram или лого) ---
    photo_url = "/static/logo.png" 
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            file = await bot.get_file(file_id)
            photo_url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file.file_path}"
    except Exception as e:
        logger.warning(f"WebApp: Не удалось загрузить фото для {user_id}: {e}")

    # --- 2. Логика Статуса ---
    is_paid = user_data.get("is_paid", False)
    demo_count = user_data.get("demo_count", 1)
    
    if is_paid:
        status_label = "Premium 👑"
    else:
        status_label = f"Демо {demo_count}"

    # --- 3. Уровни (3 челленджа = +1 уровень) ---
    challenges = user_data.get("challenges", [])
    completed_challenges = len([c for c in challenges if isinstance(c, dict) and c.get("completed")])
    
    if completed_challenges <= 2: lvl_key = "level_0"
    elif completed_challenges <= 5: lvl_key = "level_1"
    elif completed_challenges <= 8: lvl_key = "level_2"
    elif completed_challenges <= 11: lvl_key = "level_3"
    else: lvl_key = "level_4"
    
    user_level = t(lvl_key, lang)

    # --- 4. Расчет оставшихся дней и Батарейки ---
    days_val = get_remaining_days(user_data)
    
    # Расчет процента для визуализации батарейки
    # Для премиума шкала от 30 дней, для демо от 5 дней
    max_days = 30 if is_paid else 5
    battery_pct = int((days_val / max_days) * 100) if max_days > 0 else 0
    battery_pct = max(0, min(100, battery_pct))

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "name": user_data.get("name") or "Пользователь",
        "photo_url": photo_url,
        "status_text": status_label,
        "level_text": user_level,
        "accepted": len(challenges),
        "completed": completed_challenges,
        "days_left": days_val,
        "battery_pct": battery_pct,  # Исправлено: теперь передаем переменную
        "lang": lang,
        "t": t 
    })

# --- ОСТАЛЬНЫЕ АДМИН-РОУТЫ ---
@router.post("/set_timezone_auto")
async def set_timezone_auto(request: Request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        tz_offset = data.get("offset") 
        if user_id and tz_offset is not None:
            hours = -int(tz_offset) // 60
            tz_name = f"UTC{'+' if hours >= 0 else ''}{hours}"
            await db.update_user(int(user_id), timezone=tz_name)
            return {"status": "ok", "tz": tz_name}
    except Exception as e:
        logger.error(f"Ошибка авто-настройки TZ: {e}")
    return {"status": "error"}

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@router.post("/login")
async def login(request: Request, response: Response, username: str = Form(...), password: str = Form(...), totp_code: str = Form(...)):
    if not (secrets.compare_digest(username, settings.ADMIN_USERNAME) and secrets.compare_digest(password, settings.ADMIN_PASSWORD)):
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
    users_list: List[Dict[str, Any]] = []
    for user_id_str, user_data in all_users_data.items():
        try:
            user_id = int(user_id_str)
            is_expired = await is_demo_expired(user_data)
            remaining_days = get_remaining_days(user_data)
            users_list.append({
                "id": user_id,
                "name": user_data.get("name", "Unknown"),
                "username": user_data.get("username", "N/A"),
                "lang_display": get_user_lang(user_data).upper(),
                "status": "Paid" if user_data.get("is_paid") else ("Expired" if is_expired else "Demo"),
                "is_active": bool(user_data.get("active", False)),
                "remaining_days": remaining_days,
                "timezone": user_data.get("timezone", "")
            })
        except: continue
    users_list.sort(key=lambda u: (u['status'] != 'Paid', u['status'] == 'Expired', -u['remaining_days']))
    return templates.TemplateResponse("admin.html", {"request": request, "users": users_list, "total_users": len(all_users_data), "admin_secret": settings.ADMIN_SECRET})

@router.post("/action")
async def admin_action(request: Request, user_id: str = Form(...), action: str = Form(...), secret_token: str = Form(...), auth = Depends(require_admin)):
    if secret_token != settings.ADMIN_SECRET: raise HTTPException(status_code=403)
    try: uid = int(user_id)
    except: return RedirectResponse("/admin", status_code=303)
    if action == "delete_user": await db.delete_user(uid)
    elif action == "give_premium":
        await db.update_user(uid, is_paid=True, status="active_paid", active=True)
    elif action == "reset_demo":
        await db.update_user(uid, is_paid=False, demo_count=1, active=True, status="active_demo", challenges=[], challenge_streak=0)
    return RedirectResponse("/admin", status_code=303)