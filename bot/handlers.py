from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import List
import os
from datetime import datetime
import sys
from pathlib import Path

# Добавляем родительскую директорию в путь
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from utils.table_generator import TableGenerator
from utils.data_models import AnalysisResult

from keyboards import (
    get_main_menu,
    get_mode_keyboard,
    get_confirmation_keyboard,
    get_back_keyboard,
    get_top_k_keyboard
)
from analyzer import analyze_profiles
from messages import MESSAGES

router = Router()


class AnalysisStates(StatesGroup):
    waiting_for_mode = State()
    waiting_for_top_k = State()
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
    
    # Теперь спрашиваем количество профилей для анализа
    await callback.message.edit_text(
        f"📊 Режим: **{mode_text}**\n\n"
        f"🔢 Выберите количество профилей для анализа через AI:\n"
        f"(остальные профили также будут включены в результат, но без детального анализа)",
        reply_markup=get_top_k_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(AnalysisStates.waiting_for_top_k)


@router.callback_query(F.data.startswith("top_k_"), AnalysisStates.waiting_for_top_k)
async def select_top_k(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Извлекаем число из callback_data
    top_k = int(callback.data.split("_")[2])
    await state.update_data(top_k=top_k)
    
    data = await state.get_data()
    mode = data.get("mode", "professional")
    mode_text = "Professional" if mode == "professional" else "Personal"
    
    if mode == "personal":
        info_text = MESSAGES["personal_info"]
    else:
        info_text = MESSAGES["professional_info"]
    
    analysis_info = f"🔍 Анализ через AI: **{top_k} профилей**" if top_k > 0 else "🔍 **Без AI анализа** (только ранжирование по близости)"
    
    await callback.message.edit_text(
        f"📊 Режим: **{mode_text}**\n"
        f"{analysis_info}\n\n"
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
    top_k = data.get("top_k", 10)
    mode_text = "Professional" if mode == "professional" else "Personal"
    
    analysis_info = f"**Анализ через AI:** {top_k} профилей" if top_k > 0 else "**Анализ через AI:** Отключен (только ранжирование)"
    
    await message.answer(
        f"📋 **Подтверждение анализа:**\n\n"
        f"**Режим:** {mode_text}\n"
        f"{analysis_info}\n"
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
    top_k = data.get("top_k", 10)
    
    if top_k > 0:
        status_text = f"🔍 Анализирую профили...\n" \
                     f"Обрабатываю {top_k} профилей через AI\n" \
                     f"Это может занять несколько секунд."
    else:
        status_text = f"🔍 Ранжирую профили по близости...\n" \
                     f"Без детального AI анализа\n" \
                     f"Это займет пару секунд."
    
    status_message = await callback.message.edit_text(
        status_text,
        reply_markup=None
    )
    
    try:
        results = await analyze_profiles(criteria, mode, top_k)
        
        if not results:
            await status_message.edit_text(
                "😔 К сожалению, не найдено профилей в базе данных.",
                reply_markup=get_main_menu()
            )
        else:
            # Теперь results содержит объекты AnalysisResult
            matched = [r for r in results if r.matches]
            analyzed_count = sum(1 for r in results if r.reasoning)  # Сколько было проанализировано через AI
            
            # Формируем сообщение о результатах
            if matched:
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
            else:
                # Нет совпадений, но показываем статистику
                if analyzed_count > 0:
                    await status_message.edit_text(
                        f"📊 Результаты анализа:\n"
                        f"• Всего профилей: {len(results)}\n"
                        f"• Проанализировано через AI: {analyzed_count}\n"
                        f"• Найдено соответствий: 0\n\n"
                        f"Все профили отсортированы по косинусной близости в CSV файле.",
                        parse_mode="Markdown"
                    )
                else:
                    await status_message.edit_text(
                        f"📊 Результаты ранжирования:\n"
                        f"• Всего профилей: {len(results)}\n"
                        f"• Анализ через AI: отключен\n\n"
                        f"Все профили отсортированы по косинусной близости в CSV файле.",
                        parse_mode="Markdown"
                    )
            
            # ВСЕГДА создаем и отправляем CSV файл
            csv_path = TableGenerator.generate_csv(
                analysis_results=results,
                criteria=criteria,
                mode=mode,
                include_all_profiles=True  # Включаем все профили
            )
            
            # Формируем подпись для CSV в зависимости от ситуации
            if analyzed_count > 0:
                csv_caption = f"📊 CSV файл с результатами анализа\n"
                if matched:
                    csv_caption += f"✓ Найдено соответствий: {len(matched)}\n"
                else:
                    csv_caption += f"Соответствий не найдено из {analyzed_count} проанализированных\n"
                csv_caption += f"Все {len(results)} профилей отсортированы по косинусной близости"
            else:
                csv_caption = f"📊 CSV файл с результатами ранжирования\n"
                csv_caption += f"Все {len(results)} профилей отсортированы по косинусной близости\n"
                csv_caption += f"(AI анализ был отключен)"
            
            await callback.message.answer_document(
                FSInputFile(csv_path, filename=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
                caption=csv_caption
            )
            
            os.remove(csv_path)
            
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
        # Возвращаемся к выбору количества профилей
        data = await state.get_data()
        mode = data.get("mode", "professional")
        mode_text = "Professional" if mode == "professional" else "Personal"
        
        await callback.message.edit_text(
            f"📊 Режим: **{mode_text}**\n\n"
            f"🔢 Выберите количество профилей для анализа через AI:\n"
            f"(остальные профили также будут включены в результат, но без детального анализа)",
            reply_markup=get_top_k_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(AnalysisStates.waiting_for_top_k)
    elif current_state == AnalysisStates.waiting_for_top_k:
        # Возвращаемся к выбору режима
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


def format_results(results: List, total: int) -> str:
    text = f"✅ **Результаты анализа**\n\n"
    text += f"Найдено совпадений: **{len(results)}** из {total} профилей\n\n"
    
    for i, result in enumerate(results[:10], 1):
        text += f"**{i}. {result.profile_name}**\n"
        text += f"💡 {result.reasoning[:200] if result.reasoning else 'Соответствует критерию'}"
        if result.reasoning and len(result.reasoning) > 200:
            text += "..."
        text += f"\n📊 Близость: {result.similarity_score:.3f}\n\n"
    
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


