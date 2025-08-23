from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🔍 Начать анализ", callback_data="start_analysis")
    )
    builder.row(
        InlineKeyboardButton(text="ℹ️ О боте", callback_data="about"),
        InlineKeyboardButton(text="📚 Помощь", callback_data="help")
    )
    
    return builder.as_markup()


def get_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="💼 Professional", callback_data="mode_professional")
    )
    builder.row(
        InlineKeyboardButton(text="👨‍👩‍👧‍👦 Personal", callback_data="mode_personal")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    )
    
    return builder.as_markup()


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_analysis"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    )
    
    return builder.as_markup()


def get_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back")
    )
    
    return builder.as_markup()