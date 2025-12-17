from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

main_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='🎉 Начать разговор', callback_data='start_session')
        ],
        [
            InlineKeyboardButton(text='🧠 Анализ личности', callback_data='get_portrait'),
            InlineKeyboardButton(text='⚙️ Настройка акцента', callback_data='start_style_selection'),
        ],
        [
            InlineKeyboardButton(text='📈 Дневник эмоций', callback_data='start_progress_scale'),
            InlineKeyboardButton(text='📊 Мой прогресс', callback_data='get_user_stats')
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
        [
            InlineKeyboardButton(text="🌐 Наш сайт", url="https://innertalk.tilda.ws/"),
            InlineKeyboardButton(text="📣 Наш канал", url="https://t.me/InnerTalk_official")
        ],
        [
            InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="main_menu")
        ]
    ])

onboarding_step1 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Далее ➡️", callback_data="onb_next_1")],
        [InlineKeyboardButton(text="Пропустить ⏩", callback_data="onb_skip")]
    ]
)

onboarding_step2 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Далее ➡️", callback_data="onb_next_2")],
        [InlineKeyboardButton(text="Пропустить ⏩", callback_data="onb_skip")]
    ]
)

onboarding_step3 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='🤗 Выбрать акцент', callback_data='start_style_selection')],
        [InlineKeyboardButton(text='📈 Сделать первую оценку', callback_data='start_progress_scale')],
        [InlineKeyboardButton(text='✅ Готово', callback_data='onb_finish')],
        [InlineKeyboardButton(text='Пропустить ⏩', callback_data='onb_skip')]
    ]
)

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


def portrait_pagination_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    prev_btn = InlineKeyboardButton(text="⬅️", callback_data=f"portrait_page:{current_page-1}") if current_page > 1 else None
    next_btn = InlineKeyboardButton(text="➡️", callback_data=f"portrait_page:{current_page+1}") if current_page < total_pages else None

    row = []
    if prev_btn:
        row.append(prev_btn)
    row.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
    if next_btn:
        row.append(next_btn)

    kb_rows = []
    if row:
        kb_rows.append(row)
    kb_rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

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

admin_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="✉️ Рассылка", callback_data="admin_news")
        ]
    ])

back_to_admin_panel = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="admin_panel")]
    ])


mailing_segments_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Все пользователи", callback_data="mail_seg:all")
        ],
        [
            InlineKeyboardButton(text="Активные 7 дней", callback_data="mail_seg:active7")
        ],
        [
            InlineKeyboardButton(text="Есть портрет", callback_data="mail_seg:has_portrait")
        ],
        [
            InlineKeyboardButton(text="≥3 оценок", callback_data="mail_seg:scores3")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="mail_cancel")
        ]
    ]
)

mailing_confirm_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="mail_send")
        ],
        [
            InlineKeyboardButton(text="✏️ Изменить сегмент", callback_data="mail_change_segment")
        ],
        [
            InlineKeyboardButton(text="🛑 Отмена", callback_data="mail_cancel")
        ]
    ]
)