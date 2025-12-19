from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from src import states
from src.presentation import keyboards, photos
from src.presentation import texts

router = Router()


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    
    if current_state in [states.TestStates.in_test, states.TestStates.picking_test, 
                         states.TestStates.picking_length, states.TestStates.disclaimer]:
        current_data = await state.get_data()
        ai_style = current_data.get("ai_style")
        await state.set_data({"ai_style": ai_style} if ai_style else {})
    
    await state.set_state(states.SessionStates.idle)

    current_data = await state.get_data()

    if current_data.get('portrait_loading') is True and current_data.get(
            'loading_message_id') == callback.message.message_id:
        await state.update_data(portrait_loading=False, loading_message_id=None)

    caption_text = texts.MAIN_MENU_CAPTION

    try:
        new_media = InputMediaPhoto(
            media=photos.main_photo,
            caption=caption_text
        )
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.main_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.main_menu
        )

    await callback.answer()


@router.callback_query(F.data == "about_us")
async def about_us_handler(callback: CallbackQuery) -> None:
    caption_text = texts.ABOUT_US_CAPTION
    new_media = InputMediaPhoto(
        media=photos.about_us_photo,
        caption=caption_text
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.about_us_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.about_us_menu
        )

    await callback.answer()


@router.callback_query(F.data == "call_support")
async def call_support_handler(callback: CallbackQuery) -> None:
    caption_text = texts.SUPPORT_CAPTION

    new_media = InputMediaPhoto(
        media=photos.support_photo,
        caption=caption_text
    )

    try:
        await callback.message.edit_media(
            media=new_media,
            reply_markup=keyboards.support_menu
        )
    except TelegramBadRequest:
        await callback.message.edit_caption(
            caption=caption_text,
            reply_markup=keyboards.support_menu
        )

    await callback.answer()

