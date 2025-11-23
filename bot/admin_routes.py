# 11 - bot/admin_routes.py
# FastAPI роуты для админки/Админ-панель FastAPI роуты

import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from config import settings
from database import db 
from utils import get_demo_days, settings as utils_settings # settings нужен для REGULAR_DEMO_DAYS

router = APIRouter(prefix="/admin", tags=["admin"])

# ✅ ИСПРАВЛЕНО: путь теперь просто "templates", так как папка в корне
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверка логина и пароля."""
    correct_username = secrets.compare_digest(credentials.username, settings.ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, settings.ADMIN_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, username: str = Depends(check_auth)):
    """Главная страница админки."""
    # Загружаем свежие данные из БД при каждом заходе
    users_db_cache = await db.get_all_users()
    request.app.state.users_db = users_db_cache # Обновляем кэш
    
    return templates.TemplateResponse(
        "admin.html", 
        {
            "request": request,
            "users": users_db_cache,
            "total_users": len(users_db_cache)
        }
    )

@router.post("/action")
async def admin_action(
    request: Request,
    user_id: str = Form(...),
    action: str = Form(...),
    username: str = Depends(check_auth)
):
    """
    Обработка кнопок действий.
    """
    user_id_int = int(user_id)
    # Получаем актуальные данные пользователя
    user_data = await db.get_user(user_id_int)
    
    if not user_data:
        return RedirectResponse(url="/admin", status_code=303)

    # --- Логика действий (сразу пишем в БД) ---
    if action == "give_premium":
        new_data = {
            "is_paid": True,
            "status": "active_paid",
            "active": True,
            "demo_expiration": (datetime.now(ZoneInfo("UTC")) + timedelta(days=30)).isoformat()
        }
        await db.update_user(user_id_int, **new_data)
        
    elif action == "reset_demo":
        demo_duration = get_demo_days(user_id_int)
        
        new_data = {
            "is_paid": False,
            "demo_count": 1,
            "active": True,
            "status": "active_demo",
            # Используем settings из utils, так как settings импортирован из config (см. utils_settings)
            "demo_expiration": (datetime.now(ZoneInfo("UTC")) + timedelta(days=utils_settings.REGULAR_DEMO_DAYS)).isoformat(), 
            "sent_expiry_warning": False,
            "challenge_streak": 0,
            "last_challenge_date": None,
            "last_rules_date": None,
            "rules_shown_count": 0,
            "rules_indices_today": [],
        }
        await db.update_user(user_id_int, **new_data)
        
    elif action == "toggle_ban":
        new_active_status = not user_data.get("active", True)
        await db.update_user(user_id_int, active=new_active_status)
    
    # Принудительно обновляем кэш в памяти приложения после изменения БД
    request.app.state.users_db = await db.get_all_users()
    
    return RedirectResponse(url="/admin", status_code=303)