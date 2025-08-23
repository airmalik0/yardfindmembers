from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import List

from keyboards import (
    get_main_menu,
    get_mode_keyboard,
    get_confirmation_keyboard,
    get_back_keyboard
)
from analyzer import analyze_profiles
from messages import MESSAGES

router = Router()


class AnalysisStates(StatesGroup):
    waiting_for_mode = State()
    waiting_for_criteria = State()
    confirming_analysis = State()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        MESSAGES["welcome"],
        reply_markup=get_main_menu()
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        MESSAGES["help"],
        reply_markup=get_main_menu()
    )


@router.callback_query(F.data == "start_analysis")
async def start_analysis(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        MESSAGES["select_mode"],
        reply_markup=get_mode_keyboard()
    )
    await state.set_state(AnalysisStates.waiting_for_mode)


@router.callback_query(F.data.in_(["mode_professional", "mode_personal"]), AnalysisStates.waiting_for_mode)
async def select_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    mode = "professional" if callback.data == "mode_professional" else "personal"
    await state.update_data(mode=mode)
    
    mode_text = "Professional" if mode == "professional" else "Personal"
    
    if mode == "personal":
        info_text = MESSAGES["personal_info"]
    else:
        info_text = MESSAGES["professional_info"]
    
    await callback.message.edit_text(
        f"📊 Режим: **{mode_text}**\n\n"
        f"{info_text}\n\n"
        f"{MESSAGES['enter_criteria']}",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(AnalysisStates.waiting_for_criteria)


@router.message(AnalysisStates.waiting_for_criteria)
async def process_criteria(message: Message, state: FSMContext):
    criteria = message.text.strip()
    
    if len(criteria) < 3:
        await message.answer(
            "❌ Критерий слишком короткий. Пожалуйста, введите более подробный запрос.",
            reply_markup=get_back_keyboard()
        )
        return
    
    await state.update_data(criteria=criteria)
    data = await state.get_data()
    mode = data.get("mode", "professional")
    mode_text = "Professional" if mode == "professional" else "Personal"
    
    await message.answer(
        f"📋 **Подтверждение анализа:**\n\n"
        f"**Режим:** {mode_text}\n"
        f"**Критерий:** {criteria}\n\n"
        f"Начать анализ?",
        reply_markup=get_confirmation_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(AnalysisStates.confirming_analysis)


@router.callback_query(F.data == "confirm_analysis", AnalysisStates.confirming_analysis)
async def confirm_analysis(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    data = await state.get_data()
    mode = data.get("mode", "professional")
    criteria = data.get("criteria", "")
    
    status_message = await callback.message.edit_text(
        "🔍 Анализирую профили...\n"
        "Это может занять несколько секунд.",
        reply_markup=None
    )
    
    try:
        results = await analyze_profiles(criteria, mode)
        
        if not results:
            await status_message.edit_text(
                "😔 К сожалению, не найдено профилей, соответствующих вашему критерию.",
                reply_markup=get_main_menu()
            )
        else:
            matched = [r for r in results if r["matches"]]
            
            if not matched:
                await status_message.edit_text(
                    f"📊 Проанализировано {len(results)} профилей.\n"
                    f"К сожалению, ни один не соответствует критерию.",
                    reply_markup=get_main_menu()
                )
            else:
                response_text = format_results(matched, len(results))
                
                chunks = split_message(response_text, 4000)
                
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await status_message.edit_text(
                            chunk,
                            parse_mode="Markdown"
                        )
                    else:
                        await callback.message.answer(
                            chunk,
                            parse_mode="Markdown"
                        )
                
                await callback.message.answer(
                    "Анализ завершен! Что дальше?",
                    reply_markup=get_main_menu()
                )
                
    except Exception as e:
        await status_message.edit_text(
            f"❌ Произошла ошибка при анализе:\n{str(e)}",
            reply_markup=get_main_menu()
        )
    
    await state.clear()


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        MESSAGES["cancelled"],
        reply_markup=get_main_menu()
    )


@router.callback_query(F.data == "back")
async def go_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    current_state = await state.get_state()
    
    if current_state == AnalysisStates.waiting_for_criteria:
        await callback.message.edit_text(
            MESSAGES["select_mode"],
            reply_markup=get_mode_keyboard()
        )
        await state.set_state(AnalysisStates.waiting_for_mode)
    else:
        await state.clear()
        await callback.message.edit_text(
            MESSAGES["welcome"],
            reply_markup=get_main_menu()
        )


@router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        MESSAGES["help"],
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "about")
async def show_about(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        MESSAGES["about"],
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )


def format_results(results: List[dict], total: int) -> str:
    text = f"✅ **Результаты анализа**\n\n"
    text += f"Найдено совпадений: **{len(results)}** из {total} профилей\n\n"
    
    for i, result in enumerate(results[:10], 1):
        text += f"**{i}. {result['profile_name']}**\n"
        text += f"💡 {result['reasoning'][:200]}"
        if len(result['reasoning']) > 200:
            text += "..."
        text += "\n\n"
    
    if len(results) > 10:
        text += f"\n_... и еще {len(results) - 10} профилей_"
    
    return text


def split_message(text: str, max_length: int) -> List[str]:
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    for line in text.split('\n'):
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            if current_chunk:
                current_chunk += '\n'
            current_chunk += line
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks