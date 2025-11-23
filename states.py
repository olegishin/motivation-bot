# bot/states.py
from aiogram.fsm.state import State, StatesGroup


class GeneralStates(StatesGroup):
    """Общие состояния, которые используются в разных хендлерах"""
    waiting_for_feedback = State()      # не используется сейчас, но был
    waiting_for_language_choice = State()
    waiting_for_timezone_choice = State()
    # если будут ещё — добавим позже