"""
╔══════════════════════════════════════╗
║   🌸 ФЛОРА — Цветочный бот           ║
║   Один файл. Просто вставь токен.    ║
╚══════════════════════════════════════╝

КАК ЗАПУСТИТЬ:
1. Вставь свой BOT_TOKEN ниже (строка ~25)
2. Вставь свой ADMIN_ID ниже (строка ~26)
3. Вставь WEBAPP_URL ниже (строка ~27)
4. pip install aiogram
5. python bot.py
"""

import asyncio, json, logging, os
from pathlib import Path
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ╔══════════════════════════════════════╗
# ║  👇 ВСТАВЬ СЮДА СВОИ ДАННЫЕ         ║
# ╚══════════════════════════════════════╝
BOT_TOKEN  = os.getenv("BOT_TOKEN",  "7919060307:AAG4s1TyF7N8cRGsZS4fKDnSaRjTguGpqVE")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "1655167987"))   # ← замени на свой ID
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://v1ksssqqpon-oss.github.io/cveti20/")

# ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

router = Router()

# ══════════════════════════════════════
# ХРАНИЛИЩЕ ЗАКАЗОВ — сохраняется в файл
# Не теряется при перезапуске Railway!
# ══════════════════════════════════════
DB_FILE = Path("orders.json")

def db_load() -> dict:
    """Загружает заказы из файла."""
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Ошибка чтения orders.json: %s", e)
    return {}

def db_save(orders: dict) -> None:
    """Сохраняет заказы в файл."""
    try:
        DB_FILE.write_text(
            json.dumps(orders, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        log.error("Ошибка сохранения orders.json: %s", e)

# Загружаем при старте
ORDERS: dict = db_load()
log.info("Загружено заказов из файла: %d", len(ORDERS))

STATUSES = {
    "new":        ("🆕", "Новый"),
    "confirmed":  ("✅", "Подтверждён"),
    "preparing":  ("💐", "Собирается"),
    "delivering": ("🚚", "Едет к вам"),
    "done":       ("🎉", "Доставлен"),
    "cancelled":  ("❌", "Отменён"),
}

# ══════════════════════════════════════
# /start
# ══════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message):
    log.info("/start от user_id=%s username=%s", message.from_user.id, message.from_user.username)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌸 Открыть каталог", web_app=WebAppInfo(url=WEBAPP_URL))],
        [
            InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders"),
            InlineKeyboardButton(text="📞 Контакты",   callback_data="contacts"),
        ],
    ])
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"Привет, <b>{name}</b>! 🌸\n\n"
        f"Добро пожаловать в <b>Флора Бутик</b> — "
        f"авторские букеты с доставкой по Москве.\n\n"
        f"Нажми <b>«Открыть каталог»</b>, выбери букеты и оформи заказ!",
        reply_markup=kb,
    )

# ══════════════════════════════════════
# ПРИЁМ ЗАКАЗА ИЗ MINI APP
# ══════════════════════════════════════
@router.message(F.web_app_data)
async def got_order(message: Message, bot: Bot):
    user = message.from_user
    raw  = message.web_app_data.data

    log.info("📦 web_app_data от user_id=%s: %s", user.id, raw[:300])

    # Парсим JSON
    try:
        order = json.loads(raw)
    except Exception as e:
        log.error("Ошибка JSON от user_id=%s: %s", user.id, e)
        await message.answer("❌ Ошибка обработки заказа. Попробуй ещё раз.")
        return

    oid      = order.get("order_id") or f"ФЛ-{user.id}"
    items    = order.get("items", [])
    total    = order.get("total", 0)
    client   = order.get("client", {})
    dlv_type = order.get("delivery_type", "courier")
    delivery = "Курьер" if dlv_type == "courier" else "Самовывоз"
    discount = order.get("discount", 0)
    disc_amt = order.get("discount_amt", 0)
    dlv_price= order.get("delivery_price", 0)

    # ── Сохраняем заказ в файл ────────
    ORDERS[oid] = {
        "order_id":  oid,
        "status":    "new",
        "user_id":   user.id,
        "full_name": user.full_name,
        "username":  user.username or "",
        "client":    client,
        "items":     items,
        "total":     total,
        "delivery":  delivery,
        "discount":  discount,
        "created":   datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    db_save(ORDERS)
    log.info("✅ Заказ %s сохранён. Всего заказов: %d", oid, len(ORDERS))

    # ── Текст букетов ─────────────────
    if items:
        items_text = "\n".join(
            f"  {i.get('emoji','🌸')} {i.get('name','?')} × {i.get('qty',1)} = {i.get('price',0)*i.get('qty',1):,} ₽"
            for i in items
        )
    else:
        items_text = "  (список пуст)"

    # ── Сообщение клиенту ─────────────
    client_msg = (
        f"✅ <b>Заказ принят!</b> №\u00a0<code>{oid}</code>\n\n"
        f"<b>Ваши букеты:</b>\n{items_text}\n"
    )
    if discount:
        client_msg += f"\n🔖 Скидка {discount}%: −{disc_amt:,} ₽"
    client_msg += (
        f"\n🚚 Доставка: {'бесплатно' if dlv_price == 0 else str(dlv_price)+' ₽'}"
        f"\n💰 <b>Итого: {total:,} ₽</b>  |  {delivery}\n\n"
        f"Позвоним на <b>{client.get('phone','—')}</b> для подтверждения. 🌸\n"
        f"<i>Статус заказа придёт сюда автоматически.</i>"
    )
    await message.answer(client_msg)
    log.info("✅ Клиент user_id=%s получил подтверждение заказа %s", user.id, oid)

    # ── Сообщение администратору ──────
    addr_line = ""
    if dlv_type == "courier":
        addr = client.get("addr", "—")
        date = client.get("date", "")
        addr_line = f"\n📍 Адрес: {addr}"
        if date:
            addr_line += f"\n🕐 Время: {date}"

    note_line = f"\n📝 Примечание: {client.get('note')}" if client.get("note") else ""

    admin_text = (
        f"🛒 <b>НОВЫЙ ЗАКАЗ  #{oid}</b>\n\n"
        f"👤 {user.full_name}"
        f"{' (@' + user.username + ')' if user.username else ''}\n"
        f"📱 Телефон: {client.get('phone', '—')}"
        f"{addr_line}{note_line}\n\n"
        f"<b>Букеты:</b>\n{items_text}\n"
        f"{f'🔖 Скидка {discount}%: −{disc_amt:,} ₽{chr(10)}' if discount else ''}"
        f"🚚 Доставка: {'бесплатно' if dlv_price==0 else str(dlv_price)+' ₽'}  |  {delivery}\n"
        f"💰 <b>Итого: {total:,} ₽</b>\n\n"
        f"Статус: 🆕 <b>Новый</b>"
    )

    kb = _admin_kb(oid)

    log.info("📨 Отправляю уведомление админу ADMIN_ID=%s", ADMIN_ID)
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=kb,
        )
        log.info("✅ Админ ADMIN_ID=%s уведомлён о заказе %s", ADMIN_ID, oid)
    except Exception as e:
        log.error("❌ НЕ УДАЛОСЬ уведомить админа ADMIN_ID=%s: %s", ADMIN_ID, e)
        # Пишем в лог полную ошибку чтобы было понятно почему
        import traceback
        log.error(traceback.format_exc())

# ══════════════════════════════════════
# КЛАВИАТУРА СМЕНЫ СТАТУСА
# ══════════════════════════════════════
def _admin_kb(oid: str, current: str = "new") -> InlineKeyboardMarkup:
    btns = []
    row  = []
    for s, (icon, label) in STATUSES.items():
        if s == "new":
            continue
        mark = " ◀" if s == current else ""
        row.append(InlineKeyboardButton(
            text=f"{icon} {label}{mark}",
            callback_data=f"st:{oid}:{s}",
        ))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    return InlineKeyboardMarkup(inline_keyboard=btns)

# ══════════════════════════════════════
# СМЕНА СТАТУСА ЗАКАЗА (callback админа)
# ══════════════════════════════════════
@router.callback_query(F.data.startswith("st:"))
async def cb_set_status(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔ Нет доступа", show_alert=True)
        return

    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer("❌ Неверный формат", show_alert=True)
        return

    _, oid, new_status = parts

    if oid not in ORDERS:
        await cb.answer(f"❌ Заказ {oid} не найден в базе", show_alert=True)
        log.warning("Заказ %s не найден. Все заказы: %s", oid, list(ORDERS.keys()))
        return

    old_status = ORDERS[oid]["status"]
    ORDERS[oid]["status"] = new_status
    db_save(ORDERS)

    icon, label = STATUSES[new_status]
    log.info("Статус заказа %s: %s → %s (админ %s)", oid, old_status, new_status, cb.from_user.id)

    # Обновляем кнопки у админа
    try:
        await cb.message.edit_reply_markup(reply_markup=_admin_kb(oid, current=new_status))
    except Exception:
        pass

    await cb.answer(f"{icon} Статус → {label}")

    # Уведомляем клиента
    client_msgs = {
        "confirmed":  "✅ Ваш заказ подтверждён! Флорист приступает к работе.",
        "preparing":  "💐 Ваш букет собирается. Уже совсем скоро!",
        "delivering": "🚚 Заказ передан курьеру и едет к вам!",
        "done":       "🎉 Букет доставлен! Спасибо, что выбрали Флора Бутик 🌸",
        "cancelled":  "❌ Заказ отменён. Свяжитесь с нами: @flora_manager",
    }
    msg = client_msgs.get(new_status)
    user_id = ORDERS[oid].get("user_id")
    if msg and user_id:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"{msg}\n\n<b>Заказ</b> №\u00a0<code>{oid}</code>",
            )
        except Exception as e:
            log.warning("Не удалось уведомить клиента user_id=%s: %s", user_id, e)

# ══════════════════════════════════════
# КОМАНДЫ АДМИНИСТРАТОРА
# ══════════════════════════════════════
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        f"🌸 <b>Панель администратора</b>\n\n"
        f"Твой ID: <code>{message.from_user.id}</code>\n\n"
        f"/orders — все заказы\n"
        f"/stats — статистика\n\n"
        f"Статусы меняются кнопками под каждым заказом в этом чате."
    )

@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    # Перезагружаем из файла на случай если данные обновились
    orders = db_load()
    if not orders:
        await message.answer("📭 Заказов пока нет.")
        return
    text = f"📦 <b>Все заказы ({len(orders)} шт.):</b>\n\n"
    for o in sorted(orders.values(), key=lambda x: x["created"], reverse=True):
        icon, label = STATUSES.get(o["status"], ("?", "?"))
        text += (
            f"{icon} <code>{o['order_id']}</code>  "
            f"<b>{o['total']:,} ₽</b>  —  {label}\n"
            f"   👤 {o['full_name']}  ·  {o['created']}\n\n"
        )
        # Telegram ограничивает длину сообщения
        if len(text) > 3500:
            await message.answer(text)
            text = ""
    if text.strip():
        await message.answer(text)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    orders = db_load()
    if not orders:
        await message.answer("📊 Статистика пуста.")
        return
    total_n  = len(orders)
    revenue  = sum(o["total"] for o in orders.values() if o["status"] == "done")
    by_st    = {}
    for o in orders.values():
        by_st[o["status"]] = by_st.get(o["status"], 0) + 1
    st_text = "\n".join(
        f"  {STATUSES.get(s,('?',''))[0]} {STATUSES.get(s,('','?'))[1]}: <b>{n}</b>"
        for s, n in by_st.items()
    )
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"📦 Всего заказов: <b>{total_n}</b>\n"
        f"💰 Выручка (выполненные): <b>{revenue:,} ₽</b>\n\n"
        f"По статусам:\n{st_text}"
    )

# ══════════════════════════════════════
# КНОПКИ КЛИЕНТА
# ══════════════════════════════════════
@router.callback_query(F.data == "my_orders")
async def cb_my_orders(cb: CallbackQuery):
    uid    = cb.from_user.id
    orders = db_load()
    my     = [o for o in orders.values() if o.get("user_id") == uid]
    if not my:
        await cb.message.answer(
            "📭 У тебя пока нет заказов.\n"
            "Открой каталог и выбери букет! 🌸"
        )
    else:
        text = "📦 <b>Твои заказы:</b>\n\n"
        for o in sorted(my, key=lambda x: x["created"], reverse=True):
            icon, label = STATUSES.get(o["status"], ("?", "?"))
            text += (
                f"{icon} <code>{o['order_id']}</code>  {o['total']:,} ₽\n"
                f"   {label}  ·  {o['created']}\n\n"
            )
        await cb.message.answer(text)
    await cb.answer()

@router.callback_query(F.data == "contacts")
async def cb_contacts(cb: CallbackQuery):
    await cb.message.answer(
        "📞 <b>Флора Бутик</b>\n\n"
        "Менеджер: @flora_manager\n"
        "Телефон: +7 (495) 000-00-00\n"
        "Режим работы: 9:00 — 22:00 ежедневно"
    )
    await cb.answer()

# ══════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════
async def main():
    log.info("=" * 50)
    log.info("✦ Флора Бот запускается...")
    log.info("ADMIN_ID = %s", ADMIN_ID)
    log.info("WEBAPP_URL = %s", WEBAPP_URL)
    log.info("Заказов в базе: %d", len(ORDERS))
    log.info("=" * 50)

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("✦ Бот успешно запущен! Жду заказы...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
