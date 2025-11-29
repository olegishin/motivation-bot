# 13 - bot/admin_routes.py
# FastAPI роуты для админки (JWT + TOTP Auth)
# bot/admin_routes.py — НАСТОЯЩАЯ 2FA + JWT + CSRF (2025)

import secrets
import pyotp
import jwt
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Depends, HTTPException, Form, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.config import settings, logger
from bot.database import db
from bot.utils import get_demo_days

router = APIRouter(prefix="/admin", tags=["admin"])
# ✅ Используем путь templates, как настроено в main.py
templates = Jinja2Templates(directory="bot/templates") 

# --- TOTP ---
# Инициализация TOTP. ADMIN_2FA_SECRET находится в bot/config.py
totp = pyotp.TOTP(settings.ADMIN_2FA_SECRET, interval=30)

# --- JWT Константы ---
JWT_ALGORITHM = "HS256"
JWT_EXPIRY = timedelta(days=7)

def create_jwt() -> str:
    """Создает подписанный JWT токен со сроком действия."""
    payload = {"exp": datetime.now(timezone.utc) + JWT_EXPIRY}
    return jwt.encode(payload, settings.ADMIN_JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt(token: str | None) -> bool:
    """Проверяет токен на валидность и срок действия."""
    if not token:
        return False
    try:
        jwt.decode(token, settings.ADMIN_JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except:
        return False

# --- Проверка аутентификации (Dependency) ---
async def require_admin(request: Request):
    """Dependency для защиты роутов: проверяет JWT-куку."""
    token = request.cookies.get("admin_jwt")
    if not verify_jwt(token):
        # Перенаправляем на логин с кодом 303 (See Other)
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return True

# --- Страница входа ---
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

# --- Вход (логин + пароль + TOTP) ---
@router.post("/login")
async def login(
    request: Request, # ✅ ИСПРАВЛЕНИЕ: Добавлен request для логирования и ошибок
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    totp_code: str = Form(...),
):
    # 1. Проверка логина и пароля
    if not (secrets.compare_digest(username, settings.ADMIN_USERNAME) and
            secrets.compare_digest(password, settings.ADMIN_PASSWORD)):
        return templates.TemplateResponse("admin_login.html", {
            "request": request, "error": "Неверный логин или пароль"
        })

    # 2. Проверка TOTP
    if not totp.verify(totp_code.strip(), valid_window=1):
        return templates.TemplateResponse("admin_login.html", {
            "request": request, "error": "Неверный код 2FA"
        })

    # 3. Успешно — выдаём JWT-куку
    token = create_jwt()
    response = RedirectResponse(url="/admin/", status_code=303)
    response.set_cookie(
        key="admin_jwt",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=60*60*24*7 # 7 дней
    )
    logger.info(f"Admin login OK from {request.client.host}")
    return response

# --- Выход ---
@router.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("admin_jwt")
    return response

# --- Главная админка ---
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, auth = Depends(require_admin)):
    users = await db.get_all_users()
    # Приводим ключи к int для корректной работы Jinja2 в шаблоне admin.html
    # Хотя Jinja2 может работать и со str ключами, это чище
    users_int_keys = {int(k): v for k, v in users.items() if k.isdigit()}
     
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "users": users_int_keys,
        "total_users": len(users_int_keys),
        "admin_secret": settings.ADMIN_SECRET  # для CSRF
    })

# --- Действия ---
@router.post("/action")
async def admin_action(
    request: Request,
    user_id: str = Form(...),
    action: str = Form(...),
    secret_token: str = Form(...),
    auth = Depends(require_admin) # Защита роута
):
    # CSRF-проверка
    if secret_token != settings.ADMIN_SECRET:
        logger.warning(f"CSRF Token Mismatch! Action blocked from {request.client.host}")
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    try:
        uid = int(user_id)
    except:
        return RedirectResponse("/admin", status_code=303)

    if action == "delete_user":
        # ✅ Удаление (даже если юзер не найден через get_user, удаляем по ID)
        await db.delete_user(uid)
        logger.info(f"User {uid} DELETED via Admin Panel")
        return RedirectResponse("/admin", status_code=303)

    user = await db.get_user(uid)
    if not user:
        return RedirectResponse("/admin", status_code=303)

    if action == "give_premium":
        await db.update_user(uid, is_paid=True, status="active_paid", active=True,
                             demo_expiration=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
        
    elif action == "reset_demo":
        days = get_demo_days(uid)
        # ✅ Увеличиваем счетчик демо
        new_demo_count = user.get("demo_count", 0) + 1 
        await db.update_user(uid, is_paid=False, demo_count=new_demo_count, active=True, status="active_demo",
                             demo_expiration=(datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
                             sent_expiry_warning=False, challenge_streak=0,
                             last_challenge_date=None, last_rules_date=None)
                             
    elif action == "toggle_ban":
        await db.update_user(uid, active=not user.get("active", True))

    return RedirectResponse("/admin", status_code=303)