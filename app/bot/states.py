"""FSM states."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    education = State()
    faculty = State()
    course = State()
    group = State()
    confirm = State()


class SettingsFlow(StatesGroup):
    menu = State()
    education = State()
    faculty = State()
    course = State()
    group = State()
    confirm = State()
