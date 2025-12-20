import logging
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest

from src import states
from src.presentation import keyboards, photos, texts
from src import tests_data

logger = logging.getLogger(__name__)
router = Router()


async def _save_test_result_async(collection, record):
    try:
        await collection.insert_one(record)
    except Exception as e:
        logger.error(f"MongoDB error saving test result: {e}")


def _likert_options() -> list[tuple[str, str]]:
    return [("1", "test_answer:1"), ("2", "test_answer:2"), ("3", "test_answer:3"), ("4", "test_answer:4"), ("5", "test_answer:5")]


def _mbti_options() -> list[tuple[str, str]]:
    return [("Да", "test_answer:A"), ("Нет", "test_answer:B")]


async def _send_question(callback: CallbackQuery, state: FSMContext, *, first: bool = False) -> None:
    data = await state.get_data()
    test_id: str = data.get("test_id")
    version: str = data.get("version")
    idx: int = data.get("current_index", 0)
    questions = tests_data.TESTS[test_id]["versions"][version]
    total = len(questions)
    q = questions[idx]

    if q.qtype == "likert":
        options = _likert_options()
        hint = f"\n\n{texts.TESTS_LIKERT_HINT}"
    else:
        options = _mbti_options()
        hint = ""
    
    show_back = idx > 0
    kb = keyboards.question_keyboard(options, show_end=True, show_back=show_back)
    
    question_text = f"Вопрос {idx+1}/{total}:\n{q.text}{hint}"

    if first:
        try:
            await callback.message.edit_caption(
                caption=question_text,
                reply_markup=kb
            )
        except TelegramBadRequest:
            sent = await callback.message.answer(question_text, reply_markup=kb)
            await state.update_data(last_question_message_id=sent.message_id)
        else:
            await state.update_data(last_question_message_id=callback.message.message_id)
    else:
        msg_id = data.get("last_question_message_id", callback.message.message_id)
        try:
            await callback.message.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=msg_id,
                caption=question_text,
                reply_markup=kb
            )
        except TelegramBadRequest:
            sent = await callback.message.answer(question_text, reply_markup=kb)
            await state.update_data(last_question_message_id=sent.message_id)


@router.callback_query(F.data == "tests_menu")
async def tests_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(states.TestStates.disclaimer)
    new_media = InputMediaPhoto(
        media=photos.main_photo, # replace from main_photo to tests_photo when I get photo for tests
        # media=photos.tests_photo,
        caption=texts.TESTS_DISCLAIMER
    )
    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.tests_disclaimer_keyboard()
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=texts.TESTS_DISCLAIMER,
            reply_markup=keyboards.tests_disclaimer_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data == "tests_consent", StateFilter(states.TestStates.disclaimer))
async def tests_consent(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(states.TestStates.picking_test)
    await callback.message.edit_caption(caption=texts.TESTS_INTRO, reply_markup=keyboards.tests_pick_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("test_pick:"), StateFilter(states.TestStates.picking_test))
async def test_pick(callback: CallbackQuery, state: FSMContext) -> None:
    test_id = callback.data.split(":", 1)[1]
    if test_id not in tests_data.TESTS:
        await callback.answer("Неизвестный тест", show_alert=True)
        return
    await state.update_data(test_id=test_id)
    await state.set_state(states.TestStates.picking_length)
    try:
        await callback.message.edit_caption(
            caption=f"Тест: {tests_data.TESTS[test_id]['title']}\nВыберите версию:",
            reply_markup=keyboards.tests_length_keyboard()
        )
    except TelegramBadRequest:
        await callback.message.answer(
            f"Тест: {tests_data.TESTS[test_id]['title']}\nВыберите версию:",
            reply_markup=keyboards.tests_length_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data == "tests_pick_back", StateFilter(states.TestStates.picking_length))
async def tests_pick_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(states.TestStates.picking_test)
    try:
        await callback.message.edit_caption(
            caption=texts.TESTS_INTRO,
            reply_markup=keyboards.tests_pick_keyboard()
        )
    except TelegramBadRequest:
        await callback.message.answer(
            texts.TESTS_INTRO,
            reply_markup=keyboards.tests_pick_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data.startswith("test_len:"), StateFilter(states.TestStates.picking_length))
async def test_len(callback: CallbackQuery, state: FSMContext) -> None:
    version = callback.data.split(":", 1)[1]
    data = await state.get_data()
    test_id = data.get("test_id")
    if not test_id or test_id not in tests_data.TESTS:
        await callback.answer("Ошибка выбора теста", show_alert=True)
        return
    if version not in tests_data.TESTS[test_id]["versions"]:
        await callback.answer("Неизвестная версия", show_alert=True)
        return
    await state.update_data(
        version=version,
        current_index=0,
        answers=[],
        last_question_message_id=callback.message.message_id,
        test_started_at=datetime.now(timezone.utc)
    )
    await state.set_state(states.TestStates.in_test)
    await _send_question(callback, state, first=True)
    await callback.answer()


@router.callback_query(F.data.startswith("test_answer:"), StateFilter(states.TestStates.in_test))
async def test_answer(callback: CallbackQuery, state: FSMContext, users_collection) -> None:
    val = callback.data.split(":", 1)[1]
    data = await state.get_data()
    test_id: str = data.get("test_id")
    version: str = data.get("version")
    idx: int = data.get("current_index", 0)
    answers: list = data.get("answers", [])
    questions = tests_data.TESTS[test_id]["versions"][version]

    answers.append(val)
    idx += 1
    await state.update_data(answers=answers, current_index=idx)

    if idx >= len(questions):
        result = tests_data.compute_result(test_id, version, answers)
        record = {
            "user_id": callback.from_user.id,
            "type": "test_result",
            "test_id": test_id,
            "test_title": tests_data.TESTS[test_id]["title"],
            "version": version,
            "started_at": data.get("test_started_at"),
            "finished_at": datetime.now(timezone.utc),
            "answers": answers,
            "result": result,
        }
        try:
            asyncio.create_task(_save_test_result_async(users_collection, record))
        except Exception as e:
            logger.error(f"Error scheduling test result save: {e}")

        verdict_text = result.get("verdict", "Результаты обработаны.")
        msg_id = data.get("last_question_message_id", callback.message.message_id)
        try:
            await callback.message.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=msg_id,
                caption=f"✅ Тест завершён!\n\n{verdict_text}",
                reply_markup=keyboards.back_to_menu_keyboard
            )
        except TelegramBadRequest:
            await callback.message.answer(
                f"✅ Тест завершён!\n\n{verdict_text}",
                reply_markup=keyboards.back_to_menu_keyboard
            )
        await state.clear()
        await callback.answer()
        return

    await _send_question(callback, state)
    await callback.answer()


@router.callback_query(F.data == "test_prev_question", StateFilter(states.TestStates.in_test))
async def test_prev_question(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    idx: int = data.get("current_index", 0)
    answers: list = data.get("answers", [])
    
    if idx <= 0:
        await callback.answer("Это первый вопрос", show_alert=True)
        return
    
    idx -= 1
    if len(answers) > 0:
        answers.pop()
    
    await state.update_data(current_index=idx, answers=answers)
    await _send_question(callback, state)
    await callback.answer()


@router.callback_query(F.data == "end_test", StateFilter(states.TestStates.in_test))
async def end_test(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    msg_id = data.get("last_question_message_id", callback.message.message_id)
    await state.clear()
    caption_text = texts.MAIN_MENU_CAPTION
    try:
        new_media = InputMediaPhoto(
            media=photos.main_photo,
            caption=caption_text
        )
        await callback.message.bot.edit_message_media(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            media=new_media,
            reply_markup=keyboards.main_menu
        )
    except TelegramBadRequest:
        try:
            await callback.message.bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=msg_id,
                caption=caption_text,
                reply_markup=keyboards.main_menu
            )
        except TelegramBadRequest:
            await callback.message.answer_photo(
                photo=photos.main_photo,
                caption=caption_text,
                reply_markup=keyboards.main_menu
            )
    await callback.answer("Тест завершён. Данные не сохранены.")
