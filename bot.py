"""
╔══════════════════════════════════════╗
║   🌸 ФЛОРА — Цветочный бот           ║
║   Один файл. Просто вставь токен.    ║
╚══════════════════════════════════════╝

КАК ЗАПУСТИТЬ:
1. Вставь свой BOT_TOKEN ниже (строка 20)
2. Вставь свой ADMIN_ID ниже (строка 21) 
3. Вставь WEBAPP_URL ниже (строка 22)
4. pip install aiogram python-dotenv
5. python bot.py
"""

import asyncio, json, logging
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
BOT_TOKEN  = "7919060307:AAG4s1TyF7N8cRGsZS4fKDnSaRjTguGpqVE"        # от @BotFather
ADMIN_ID   =  1655167987               # твой Telegram ID (от @userinfobot)
WEBAPP_URL = "ВСТАВЬ_ССЫЛКУ_НА_INDEX_HTML"  # https://... (адрес index.html)

# ──────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

router = Router()

# Хранилище заказов в памяти (сбрасывается при перезапуске)
# Для постоянного хранения — см. database.py в полной версии
ORDERS: dict[str, dict] = {}

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
    try:
        order = json.loads(message.web_app_data.data)
    except Exception:
        await message.answer("❌ Ошибка. Попробуй ещё раз.")
        return

    oid   = order.get("order_id", "???")
    items = order.get("items", [])
    total = order.get("total", 0)
    client = order.get("client", {})
    delivery = "Курьер" if order.get("delivery_type") == "courier" else "Самовывоз"

    # Сохраняем заказ
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
        "discount":  order.get("discount", 0),
        "created":   datetime.now().strftime("%d.%m.%Y %H:%M"),
    }

    # Список букетов
    items_text = "\n".join(
        f"  {i['emoji']} {i['name']} × {i['qty']} = {i['price']*i['qty']:,} ₽"
        for i in items
    )

    # ── Клиенту ──────────────────────
    await message.answer(
        f"✅ <b>Заказ принят!</b> №\u00a0<code>{oid}</code>\n\n"
        f"<b>Ваши букеты:</b>\n{items_text}\n\n"
        f"<b>Итого: {total:,} ₽</b>  |  {delivery}\n\n"
        f"Позвоним на <b>{client.get('phone','—')}</b> для подтверждения. 🌸\n"
        f"<i>Статус заказа придёт сюда автоматически.</i>"
    )

    # ── Администратору ────────────────
    addr = f"\n📍 {client.get('addr','—')}" if order.get("delivery_type") == "courier" else ""
    note = f"\n📝 {client.get('note')}" if client.get("note") else ""

    admin_text = (
        f"🛒 <b>НОВЫЙ ЗАКАЗ  #{oid}</b>\n\n"
        f"👤 {user.full_name}"
        f"{' (@'+user.username+')' if user.username else ''}\n"
        f"📱 {client.get('phone','—')}{addr}{note}\n\n"
        f"<b>Букеты:</b>\n{items_text}\n\n"
        f"💰 <b>Итого: {total:,} ₽</b>  |  {delivery}"
    )
    kb = _admin_kb(oid)
    try:
        await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb)
    except Exception as e:
        log.warning("Не удалось уведомить админа: %s", e)

# ══════════════════════════════════════
# КНОПКИ СМЕНЫ СТАТУСА (для админа)
# ══════════════════════════════════════
def _admin_kb(oid: str, current: str = "new") -> InlineKeyboardMarkup:
    btns = []
    row = []
    for s, (icon, label) in STATUSES.items():
        if s == "new":
            continue  # начальный статус, кнопку не нужна
        mark = " ◀" if s == current else ""
        row.append(InlineKeyboardButton(
            text=f"{icon} {label}{mark}",
            callback_data=f"st:{oid}:{s}",
        ))
        if len(row) == 2:
            btns.append(row); row = []
    if row:
        btns.append(row)
    return InlineKeyboardMarkup(inline_keyboard=btns)

@router.callback_query(F.data.startswith("st:"))
async def cb_set_status(cb: CallbackQuery, bot: Bot):
    # Только админ может менять статус
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔ Нет доступа")
        return

    _, oid, new_status = cb.data.split(":", 2)
    if oid not in ORDERS:
        await cb.answer("❌ Заказ не найден", show_alert=True)
        return

    ORDERS[oid]["status"] = new_status
    icon, label = STATUSES[new_status]

    # Обновляем кнопки в чате админа
    try:
        await cb.message.edit_reply_markup(reply_markup=_admin_kb(oid, current=new_status))
    except Exception:
        pass

    await cb.answer(f"{icon} {label}", show_alert=False)

    # Уведомляем клиента
    client_msgs = {
        "confirmed":  "✅ Ваш заказ подтверждён! Флорист приступает к работе.",
        "preparing":  "💐 Ваш букет собирается. Уже скоро!",
        "delivering": "🚚 Заказ передан курьеру и едет к вам!",
        "done":       "🎉 Букет доставлен! Спасибо, что выбрали Флора Бутик 🌸",
        "cancelled":  "❌ Заказ отменён. Свяжитесь с нами: @flora_manager",
    }
    msg = client_msgs.get(new_status)
    user_id = ORDERS[oid].get("user_id")
    if msg and user_id:
        try:
            await bot.send_message(user_id, f"{msg}\n\n<b>Заказ</b> <code>{oid}</code>")
        except Exception as e:
            log.warning("Не удалось уведомить клиента: %s", e)

# ══════════════════════════════════════
# КОМАНДЫ АДМИНИСТРАТОРА
# ══════════════════════════════════════
@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not ORDERS:
        await message.answer("📭 Заказов пока нет.")
        return
    text = "📦 <b>Все заказы:</b>\n\n"
    for o in sorted(ORDERS.values(), key=lambda x: x["created"], reverse=True):
        icon, label = STATUSES.get(o["status"], ("?","?"))
        text += f"{icon} <code>{o['order_id']}</code>  {o['total']:,} ₽  —  {label}\n"
        text += f"   {o['full_name']}  ·  {o['created']}\n\n"
    await message.answer(text)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not ORDERS:
        await message.answer("📊 Статистика пуста.")
        return
    total_orders = len(ORDERS)
    revenue = sum(o["total"] for o in ORDERS.values() if o["status"] == "done")
    by_status = {}
    for o in ORDERS.values():
        by_status[o["status"]] = by_status.get(o["status"], 0) + 1
    st_text = "\n".join(
        f"  {STATUSES.get(s,('?','?'))[0]} {STATUSES.get(s,('?',s))[1]}: {n}"
        for s, n in by_status.items()
    )
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"Всего заказов: <b>{total_orders}</b>\n"
        f"Выручка (выполненные): <b>{revenue:,} ₽</b>\n\n"
        f"По статусам:\n{st_text}"
    )

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "🌸 <b>Панель администратора</b>\n\n"
        "/orders — все заказы\n"
        "/stats — статистика\n\n"
        "Статусы меняются кнопками под каждым заказом."
    )

# ══════════════════════════════════════
# КНОПКИ КЛИЕНТА
# ══════════════════════════════════════
@router.callback_query(F.data == "my_orders")
async def cb_my_orders(cb: CallbackQuery):
    uid = cb.from_user.id
    my = [o for o in ORDERS.values() if o["user_id"] == uid]
    if not my:
        await cb.message.answer("📭 У тебя пока нет заказов.\nОткрой каталог и выбери букет! 🌸")
    else:
        text = "📦 <b>Твои заказы:</b>\n\n"
        for o in sorted(my, key=lambda x: x["created"], reverse=True):
            icon, label = STATUSES.get(o["status"], ("?","?"))
            text += f"{icon} <code>{o['order_id']}</code>  {o['total']:,} ₽\n"
            text += f"   {label}  ·  {o['created']}\n\n"
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
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("✦ Флора Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
