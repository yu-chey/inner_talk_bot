from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

main_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='🎉 Начать разговор', callback_data='start_session')
        ],
        [
            InlineKeyboardButton(text='🧠 Анализ личности', callback_data='get_portrait'),
            InlineKeyboardButton(text='⚙️ Настройка Акцента', callback_data='start_style_selection'),
        ],
        [
            InlineKeyboardButton(text='📈 Шкала Прогресса', callback_data='start_progress_scale'),
            InlineKeyboardButton(text='📊 Моя Статистика', callback_data='get_user_stats')
        ],
        [
            InlineKeyboardButton(text='ℹ️ О нас', callback_data='about_us'),
            InlineKeyboardButton(text='📧 Тех. поддержка', callback_data='call_support')
        ]
    ])

about_us_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="👨‍💻 Разработчик", url="https://t.me/yu_chey"),
            InlineKeyboardButton(text="👑 Владелец", url="https://t.me/zhanrin"),
            InlineKeyboardButton(text="📢 SMM", url="https://t.me/dikosua")
        ],
        # [
        #     InlineKeyboardButton(text="📸 Instagram", url="https://www.instagram.com/inn.tlk"),
        #     InlineKeyboardButton(text="🎶 TikTok", url="https://www.tiktok.com/@lnn.tlk")
        # ],
        [
            InlineKeyboardButton(text="🌐 Наш сайт", url="https://innertalk.tilda.ws/"),
            InlineKeyboardButton(text="📣 Наш канал", url="https://t.me/InnerTalk_official")
        ],
        [
            InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="main_menu")
        ]
    ])

end_session_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='🛑 Закончить разговор', callback_data="end_session")
        ]
    ])

back_to_menu_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="main_menu")
        ]
    ])

support_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="main_menu")
        ]
    ])

progress_scale_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='1 😭', callback_data='set_score:1'),
            InlineKeyboardButton(text='2 😠', callback_data='set_score:2'),
            InlineKeyboardButton(text='3 😔', callback_data='set_score:3'),
        ],
        [
            InlineKeyboardButton(text='4 😟', callback_data='set_score:4'),
            InlineKeyboardButton(text='5 😐', callback_data='set_score:5'),
            InlineKeyboardButton(text='6 🙂', callback_data='set_score:6'),
            InlineKeyboardButton(text='7 😊', callback_data='set_score:7'),
        ],
        [
            InlineKeyboardButton(text='8 🤩', callback_data='set_score:8'),
            InlineKeyboardButton(text='9 ✨', callback_data='set_score:9'),
            InlineKeyboardButton(text='10 🎉', callback_data='set_score:10'),
        ],
        [
            InlineKeyboardButton(text="⬅️ Отмена", callback_data="main_menu")
        ]
    ])

style_selection_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='🤗 Эмпатия и Поддержка', callback_data='set_style:empathy')
        ],
        [
            InlineKeyboardButton(text='🛠️ Практика и Действие', callback_data='set_style:action')
        ],
        [
            InlineKeyboardButton(text='➡️ Продолжить как обычно', callback_data='set_style:default')
        ]
    ])