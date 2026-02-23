"""
╔══════════════════════════════════════╗
║   🌸 ФЛОРА — Цветочный бот           ║
║   Полная версия с уведомлениями      ║
╚══════════════════════════════════════╝
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
# ║  👇 ТВОИ НАСТРОЙКИ                  ║
# ╚══════════════════════════════════════╝
BOT_TOKEN  = os.getenv("BOT_TOKEN",  "7919060307:AAG4s1TyF7N8cRGsZS4fKDnSaRjTguGpqVE")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "1655167987")) 
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://v1ksssqqpon-oss.github.io/cveti20/")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

router = Router()
DB_FILE = Path("orders.json")

def db_load() -> dict:
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Ошибка чтения orders.json: %s", e)
    return {}

def db_save(orders: dict) -> None:
    try:
        DB_FILE.write_text(
            json.dumps(orders, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        log.error("Ошибка сохранения orders.json: %s", e)

ORDERS: dict = db_load()

STATUSES = {
    "new":        ("🆕", "Новый"),
    "confirmed":  ("✅", "Подтверждён"),
    "preparing":  ("💐", "Собирается"),
    "delivering": ("🚚", "Едет к вам"),
    "done":       ("🎉", "Доставлен"),
    "cancelled":  ("❌", "Отменён"),
}

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
        f"Привет, <b>{name}</b>! 🌸\n\nНажми <b>«Открыть каталог»</b>, чтобы оформить заказ!",
        reply_markup=kb,
    )

# ══════════════════════════════════════
# ИСПРАВЛЕННЫЙ ПРИЁМ ЗАКАЗА
# ══════════════════════════════════════
@router.message(F.web_app_data)
async def got_order(message: Message, bot: Bot):
    user = message.from_user
    raw  = message.web_app_data.data
    
    try:
        order = json.loads(raw)
    except Exception as e:
        log.error("Ошибка JSON: %s", e)
        await message.answer("❌ Ошибка обработки заказа.")
        return

    oid      = order.get("order_id") or f"ФЛ-{user.id}"
    items    = order.get("items", [])
    total    = order.get("total", 0)
    client   = order.get("client", {})
    dlv_type = order.get("delivery_type", "courier")
    delivery = "Курьер" if dlv_type == "courier" else "Самовывоз"
    
    # Сохраняем в БД
    ORDERS[oid] = {
        "order_id": oid, "status": "new", "user_id": user.id,
        "full_name": user.full_name, "username": user.username or "",
        "client": client, "items": items, "total": total,
        "delivery": delivery, "created": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    db_save(ORDERS)

    # Формируем текст товаров
    items_text = "\n".join([f"  🌸 {i.get('name')} × {i.get('qty')} = {i.get('price')*i.get('qty'):,} ₽" for i in items])

    # Уведомление клиенту
    await message.answer(f"✅ <b>Заказ №{oid} принят!</b>\n\n<b>Букеты:</b>\n{items_text}\n\n💰 <b>Итого: {total:,} ₽</b>")

    # ПОДГОТОВКА ТЕКСТА ДЛЯ АДМИНА
    addr_line = f"\n📍 Адрес: {client.get('addr')}" if dlv_type == "courier" else ""
    admin_text = (
        f"🛒 <b>НОВЫЙ ЗАКАЗ #{oid}</b>\n\n"
        f"👤 Клиент: {user.full_name} (@{user.username or '—'})\n"
        f"📞 Тел: {client.get('phone', '—')}{addr_line}\n\n"
        f"<b>Состав:</b>\n{items_text}\n\n"
        f"💰 <b>Сумма: {total:,} ₽</b> ({delivery})"
    )

    # ОТПРАВКА АДМИНУ (ИСПРАВЛЕНО)
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=_admin_kb(oid))
        log.info("✅ Уведомление админу отправлено")
    except Exception as e:
        log.error("❌ Ошибка отправки админу: %s", e)

def _admin_kb(oid: str, current: str = "new") -> InlineKeyboardMarkup:
    btns = []
    row = []
    for s, (icon, label) in STATUSES.items():
        if s == "new": continue
        row.append(InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"st:{oid}:{s}"))
        if len(row) == 2:
            btns.append(row); row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(inline_keyboard=btns)

@router.callback_query(F.data.startswith("st:"))
async def cb_set_status(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID: return
    _, oid, new_status = cb.data.split(":")
    if oid in ORDERS:
        ORDERS[oid]["status"] = new_status
        db_save(ORDERS)
        await cb.answer(f"Статус обновлен: {new_status}")
        # Уведомление клиента о смене статуса
        try:
            icon, label = STATUSES[new_status]
            await bot.send_message(ORDERS[oid]["user_id"], f"🌸 Статус вашего заказа №{oid} изменен на: <b>{label}</b> {icon}")
        except: pass

@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = "📦 <b>Последние заказы:</b>\n\n"
    for o in list(ORDERS.values())[-10:]:
        text += f"• <code>{o['order_id']}</code>: {o['total']}₽ ({o['status']})\n"
    await message.answer(text or "Заказов нет")

async def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
