import asyncio
import logging
from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from src import config, states
from src.presentation import keyboards

logger = logging.getLogger(__name__)
router = Router()


async def get_average_messages_per_user(users_collection, cache=None):
    cache_key = "avg_messages_per_user"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return cached
    
    async def get_total_user_messages():
        return await users_collection.count_documents({"type": "user_message"})

    async def get_distinct_users_who_sent_messages():
        pipeline = [
            {"$match": {"type": "user_message"}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "distinct_users"}
        ]
        cursor = users_collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        return result[0].get("distinct_users", 0) if result else 0

    total_messages, unique_users = await asyncio.gather(
        get_total_user_messages(),
        get_distinct_users_who_sent_messages()
    )

    if unique_users == 0:
        avg = 0
    else:
        avg = total_messages / unique_users

    result = {
        "average_messages_per_user": round(avg, 2),
        "total_messages": total_messages,
        "unique_users": unique_users
    }
    
    if cache:
        await cache.set(cache_key, result, ttl=300)
    
    return result


async def _admin_metrics(users_collection, cache=None):
    cache_key = "admin_metrics"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return cached
    now = datetime.now(timezone.utc)
    d1 = now - timedelta(days=1)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    async def count_distinct(query, field):
        pipeline = [
            {"$match": query},
            {"$group": {"_id": f"${field}"}},
            {"$count": "c"}
        ]
        res = await users_collection.aggregate(pipeline).to_list(length=1)
        return (res[0]["c"] if res else 0)

    total_users = await count_distinct({"type": "user_profile"}, "user_id")
    dau = await count_distinct({"type": "user_profile", "last_active": {"$gte": d1}}, "user_id")
    wau = await count_distinct({"type": "user_profile", "last_active": {"$gte": d7}}, "user_id")
    mau = await count_distinct({"type": "user_profile", "last_active": {"$gte": d30}}, "user_id")

    new_24h = await users_collection.count_documents({"type": "user_profile", "created_at": {"$gte": d1}})
    new_7d = await users_collection.count_documents({"type": "user_profile", "created_at": {"$gte": d7}})

    active_dialogs_24h = await count_distinct({"type": "user_message", "timestamp": {"$gte": d1}}, "user_id")

    avg_msgs = await get_average_messages_per_user(users_collection, cache=None)

    pipeline_sessions = [
        {"$match": {"type": "session_summary", "timestamp": {"$gte": d7}}},
        {"$group": {"_id": None, "cnt": {"$sum": 1}, "avg_len": {"$avg": "$real_user_message_count"}}}
    ]
    sess = await users_collection.aggregate(pipeline_sessions).to_list(length=1)
    sessions_7d = int(sess[0]["cnt"]) if sess else 0
    avg_session_len = float(sess[0]["avg_len"]) if sess and sess[0]["avg_len"] is not None else 0.0

    portraits_7d = await users_collection.count_documents({"type": "user_profile", "last_portrait_timestamp": {"$gte": d7}})

    pipeline_avg7 = [
        {"$match": {"type": "progress_score", "timestamp": {"$gte": d7}}},
        {"$group": {"_id": None, "avg": {"$avg": "$score"}}}
    ]
    pipeline_prev7 = [
        {"$match": {"type": "progress_score", "timestamp": {"$lt": d7, "$gte": d7 - timedelta(days=7)}}},
        {"$group": {"_id": None, "avg": {"$avg": "$score"}}}
    ]
    a7 = await users_collection.aggregate(pipeline_avg7).to_list(length=1)
    p7 = await users_collection.aggregate(pipeline_prev7).to_list(length=1)
    avg_score_7d = float(a7[0]["avg"]) if a7 and a7[0]["avg"] is not None else 0.0
    prev_avg_score_7d = float(p7[0]["avg"]) if p7 and p7[0]["avg"] is not None else 0.0
    trend = 0.0
    if prev_avg_score_7d > 0:
        trend = (avg_score_7d - prev_avg_score_7d) / prev_avg_score_7d

    onboard_total = total_users if total_users > 0 else 1
    onboard_completed = await users_collection.count_documents({"type": "user_profile", "onboarding_completed": True})
    onboarding_conv = onboard_completed / onboard_total

    result = {
        "total_users": total_users,
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "new_24h": new_24h,
        "new_7d": new_7d,
        "active_dialogs_24h": active_dialogs_24h,
        "avg_msgs": avg_msgs,
        "sessions_7d": sessions_7d,
        "avg_session_len": avg_session_len,
        "portraits_7d": portraits_7d,
        "avg_score_7d": avg_score_7d,
        "trend": trend,
        "onboarding_conv": onboarding_conv,
    }
    
    if cache:
        await cache.set(cache_key, result, ttl=120)
    
    return result


async def _get_blacklisted_ids(users_collection) -> set[int]:
    cur = users_collection.find({"type": "blacklisted"}, {"user_id": 1, "_id": 0})
    res = set()
    async for d in cur:
        if isinstance(d.get("user_id"), int):
            res.add(d["user_id"])
    return res


async def _add_to_blacklist(users_collection, user_id: int):
    try:
        await users_collection.update_one(
            {"type": "blacklisted", "user_id": user_id},
            {"$set": {"type": "blacklisted", "user_id": user_id}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Не удалось добавить в blacklist {user_id}: {e}")


async def _segment_user_ids(users_collection, seg: str) -> list[int]:
    bl = await _get_blacklisted_ids(users_collection)
    ids: set[int] = set()
    now = datetime.now(timezone.utc)
    if seg == "all":
        cur = users_collection.find({"type": "user_profile"}, {"user_id": 1, "_id": 0})
        async for d in cur:
            uid = d.get("user_id")
            if isinstance(uid, int):
                ids.add(uid)
    elif seg == "active7":
        since = now - timedelta(days=7)
        cur = users_collection.find({"type": "user_profile", "last_active": {"$gte": since}}, {"user_id": 1, "_id": 0})
        async for d in cur:
            uid = d.get("user_id")
            if isinstance(uid, int):
                ids.add(uid)
    elif seg == "has_portrait":
        cur = users_collection.find({"type": "user_profile", "last_portrait_timestamp": {"$exists": True}}, {"user_id": 1, "_id": 0})
        async for d in cur:
            uid = d.get("user_id")
            if isinstance(uid, int):
                ids.add(uid)
    elif seg == "scores3":
        pipeline = [
            {"$match": {"type": "progress_score"}},
            {"$group": {"_id": "$user_id", "cnt": {"$sum": 1}}},
            {"$match": {"cnt": {"$gte": 3}}},
            {"$project": {"user_id": "$_id", "_id": 0}}
        ]
        async for d in users_collection.aggregate(pipeline):
            uid = d.get("user_id")
            if isinstance(uid, int):
                ids.add(uid)

    return [i for i in ids if i not in bl]


async def _send_with_retry(bot, user_id: int, text: str, *, retries: int = 3):
    delay = config.RATE_LIMIT_DELAY
    attempt = 0
    while attempt < retries:
        try:
            await bot.send_message(user_id, text)
            await asyncio.sleep(delay)
            return "ok"
        except Exception as e:
            s = str(e).lower()
            if "forbidden" in s or "blocked" in s or "403" in s:
                return "blocked"
            transient = any(x in s for x in ["429", "timeout", "temporar", "unavailable", "reset", "connection", "rate", "5"]) and "403" not in s
            attempt += 1
            if not transient or attempt >= retries:
                return f"err:{e}"
            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))


async def start_mass_mailing(bot, text: str, admin_id: int, users_collection, seg: str):
    user_ids = await _segment_user_ids(users_collection, seg)
    total = len(user_ids)
    if total == 0:
        await bot.send_message(admin_id, "Нет пользователей в выбранном сегменте.", reply_markup=keyboards.back_to_admin_panel)
        return

    sem = asyncio.Semaphore(20)
    results = {"ok": 0, "blocked": 0, "errors": 0}

    async def worker(uid: int):
        async with sem:
            res = await _send_with_retry(bot, uid, text)
            if res == "ok":
                results["ok"] += 1
            elif res == "blocked":
                results["blocked"] += 1
                await _add_to_blacklist(users_collection, uid)
            else:
                results["errors"] += 1

    await asyncio.gather(*(worker(uid) for uid in user_ids))

    async def _save_mailing_log():
        try:
            await users_collection.insert_one({
                "type": "mailing_log",
                "text": text,
                "segment": seg,
                "timestamp": datetime.now(timezone.utc),
                "total": total,
                **results
            })
        except Exception as e:
            logger.error(f"Не удалось сохранить лог рассылки: {e}")
    
    asyncio.create_task(_save_mailing_log())

    summary = (
        "✅ Рассылка завершена\n\n"
        f"Сегмент: {seg}\n"
        f"Всего: {total}\n"
        f"Доставлено: {results['ok']}\n"
        f"Заблокировали: {results['blocked']}\n"
        f"Ошибок: {results['errors']}\n"
    )
    await bot.send_message(admin_id, summary, reply_markup=keyboards.back_to_admin_panel)


@router.callback_query(F.data == "admin_panel", config.IsAdmin())
async def admin_panel(callback: CallbackQuery) -> None:
    text = (
        "👋 Добро пожаловать в Админ-панель!\n\n"
        "Вы находитесь в главном меню управления ботом."
        "Выберите действие ниже, чтобы начать работу с пользователями или системой.\n"
        "\n"
        "[Внимание] Все критические действия (рассылка, бан) запускаются "
        "через соответствующую кнопку."
    )

    await callback.message.edit_text(text=text, reply_markup=keyboards.admin_keyboard)


@router.callback_query(F.data == "admin_stats", config.IsAdmin())
async def admin_stats(callback: CallbackQuery, users_collection) -> None:
    m = await _admin_metrics(users_collection)
    avg = m["avg_msgs"]["average_messages_per_user"]
    total_messages = m["avg_msgs"]["total_messages"]

    trend_icon = "⚖️"
    if m["trend"] > 0.05:
        trend_icon = "🚀"
    elif m["trend"] < -0.05:
        trend_icon = "⬇️"

    stats = (
        "📊 Статистика InnerTalk\n\n"
        f"👥 Пользователи: {m['total_users']:,}\n"
        f"➕ Новые: 24ч {m['new_24h']:,} • 7д {m['new_7d']:,}\n\n"
        f"🟢 Активность: DAU {m['dau']:,} • WAU {m['wau']:,} • MAU {m['mau']:,}\n"
        f"💬 Сообщений всего: {total_messages:,} • в среднем: {avg:.2f}/польз.\n"
        f"🗣️ Активные диалоги (24ч): {m['active_dialogs_24h']:,}\n\n"
        f"🧵 Сессии (7д): {m['sessions_7d']:,} • средняя длина: {m['avg_session_len']:.1f} сообщений\n"
        f"🧠 Портретов (7д): {m['portraits_7d']:,}\n"
        f"📈 Средний балл (7д): {m['avg_score_7d']:.2f} ({trend_icon} тренд)\n\n"
        f"🎯 Онбординг завершили: {m['onboarding_conv']*100:.1f}%\n"
    )

    await callback.message.edit_text(text=stats, reply_markup=keyboards.back_to_admin_panel)


@router.callback_query(F.data == "admin_news", config.IsAdmin())
async def process_mailing_start(callback: CallbackQuery, state: FSMContext, users_collection):
    await callback.message.edit_text("Введите текст для рассылки:")
    await state.set_state(states.MailingStates.waiting_for_text)
    await callback.answer()


@router.callback_query(F.data.startswith("mail_seg:"), config.IsAdmin())
async def mailing_choose_segment(callback: CallbackQuery, state: FSMContext):
    seg = callback.data.split(":")[1]
    await state.update_data(mailing_segment=seg)
    data = await state.get_data()
    text = data.get("mailing_text", "")
    preview = (
        "✉️ Предпросмотр\n\n"
        f"Сегмент: {seg}\n\n"
        f"---\n{text}\n---\n\n"
        "Запустить рассылку?"
    )
    await state.set_state(states.MailingStates.waiting_for_confirmation)
    try:
        await callback.message.edit_text(preview, reply_markup=keyboards.mailing_confirm_keyboard)
    except TelegramBadRequest:
        await callback.message.answer(preview, reply_markup=keyboards.mailing_confirm_keyboard)
    await callback.answer()


@router.callback_query(F.data == "mail_change_segment", config.IsAdmin())
async def mailing_change_segment(callback: CallbackQuery, state: FSMContext):
    await state.set_state(states.MailingStates.waiting_for_text)
    await callback.message.edit_text("Выберите сегмент получателей:", reply_markup=keyboards.mailing_segments_keyboard)
    await callback.answer()


@router.callback_query(F.data == "mail_cancel", config.IsAdmin())
async def mailing_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=keyboards.back_to_admin_panel)
    await callback.answer()


@router.callback_query(F.data == "mail_send", config.IsAdmin())
async def mailing_send(callback: CallbackQuery, state: FSMContext, users_collection):
    data = await state.get_data()
    text = data.get("mailing_text", "")
    seg = data.get("mailing_segment", "all")
    await state.clear()
    asyncio.create_task(start_mass_mailing(callback.bot, text, callback.from_user.id, users_collection, seg))
    await callback.message.edit_text("🚀 Рассылка запущена. Итоги пришлю по завершении.")
    await callback.answer()
