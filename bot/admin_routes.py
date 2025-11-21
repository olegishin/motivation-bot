import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse

from config import settings
from database import db

# ✅ Роутер для Web (FastAPI)
router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="/app/bot/templates")
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
    # Получаем свежие данные из базы
    users_db_cache = await db.get_all_users()
    request.app.state.users_db = users_db_cache 
    
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
    # ✅ Берем юзера прямо из базы (надежнее, чем кэш)
    user_data = await db.get_user(user_id_int)
    
    if not user_data:
        return RedirectResponse(url="/admin", status_code=303)

    # --- Логика действий ---
    # Используем await db.update_user для сохранения
    
    if action == "give_premium":
        await db.update_user(
            user_id_int,
            is_paid=1,          # True -> 1 для SQLite
            is_active=1,        # active -> is_active
            demo_expiration=(datetime.now(ZoneInfo("UTC")) + timedelta(days=30)).isoformat()
        )
        
    elif action == "reset_demo":
        await db.update_user(
            user_id_int,
            is_paid=0,
            demo_cycles=1,      # demo_count -> demo_cycles
            is_active=1,
            demo_expiration=(datetime.now(ZoneInfo("UTC")) + timedelta(days=settings.REGULAR_DEMO_DAYS)).isoformat(),
            sent_expiry_warning=0
        )
        
    elif action == "toggle_ban":
        # Инвертируем текущий статус
        current_status = user_data.get("is_active", 1)
        new_active_status = 0 if current_status else 1
        await db.update_user(user_id_int, is_active=new_active_status)
    
    return RedirectResponse(url="/admin", status_code=303)