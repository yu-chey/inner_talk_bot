import logging
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest

from src import states
from src.presentation import keyboards, photos, texts

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "onb_next_1", StateFilter(states.OnboardingStates.step1))
async def onboarding_next_1(callback: CallbackQuery, state: FSMContext):
    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=texts.ONBOARDING_STEP2
    )
    try:
        await callback.message.edit_media(media=new_media, reply_markup=keyboards.onboarding_step2)
    except TelegramBadRequest:
        await callback.message.edit_caption(caption=texts.ONBOARDING_STEP2, reply_markup=keyboards.onboarding_step2)
    await state.set_state(states.OnboardingStates.step2)
    await callback.answer()


@router.callback_query(F.data == "onb_next_2", StateFilter(states.OnboardingStates.step2))
async def onboarding_next_2(callback: CallbackQuery, state: FSMContext):
    new_media = InputMediaPhoto(
        media=photos.main_photo,
        caption=texts.ONBOARDING_STEP3
    )
    try:
        await callback.message.edit_media(media=new_media, reply_markup=keyboards.onboarding_step3)
    except TelegramBadRequest:
        await callback.message.edit_caption(caption=texts.ONBOARDING_STEP3, reply_markup=keyboards.onboarding_step3)
    await state.set_state(states.OnboardingStates.step3)
    await callback.answer()


async def _finish_onboarding(callback: CallbackQuery, users_collection, state: FSMContext):
    user_id = callback.from_user.id
    try:
        await users_collection.update_one(
            {"user_id": user_id, "type": "user_profile"},
            {"$set": {"onboarding_completed": True}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Ошибка обновления статуса онбординга: {e}")

    await state.set_state(states.SessionStates.idle)
    caption_text = texts.MAIN_MENU_CAPTION
    new_media = InputMediaPhoto(media=photos.main_photo, caption=caption_text)
    try:
        await callback.message.edit_media(media=new_media, reply_markup=keyboards.main_menu)
    except TelegramBadRequest:
        await callback.message.edit_caption(caption=caption_text, reply_markup=keyboards.main_menu)
    await callback.answer()


@router.callback_query(F.data == "onb_finish", StateFilter(states.OnboardingStates.step3))
async def onboarding_finish(callback: CallbackQuery, users_collection, state: FSMContext):
    await _finish_onboarding(callback, users_collection, state)


@router.callback_query(F.data == "onb_skip", StateFilter(states.OnboardingStates.step1, states.OnboardingStates.step2, states.OnboardingStates.step3))
async def onboarding_skip(callback: CallbackQuery, users_collection, state: FSMContext):
    await _finish_onboarding(callback, users_collection, state)

