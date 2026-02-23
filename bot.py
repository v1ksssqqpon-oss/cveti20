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

# ══════════════════════════════════════
# НАСТРОЙКИ
# ══════════════════════════════════════
BOT_TOKEN  = "7919060307:AAG4s1TyF7N8cRGsZS4fKDnSaRjTguGpqVE"
ADMIN_ID   = 1655167987  # Твой ID
WEBAPP_URL = "https://v1ksssqqpon-oss.github.io/cveti20/"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

router = Router()
DB_FILE = Path("orders.json")

def db_load():
    if DB_FILE.exists():
        try: return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except: return {}
    return {}

def db_save(orders):
    try:
        DB_FILE.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.error(f"Ошибка сохранения файла: {e}")

ORDERS = db_load()

STATUSES = {
    "new": ("🆕", "Новый"),
    "confirmed": ("✅", "Подтверждён"),
    "preparing": ("💐", "Собирается"),
    "delivering": ("🚚", "Едет к вам"),
    "done": ("🎉", "Доставлен"),
    "cancelled": ("❌", "Отменён"),
}

# ══════════════════════════════════════
# КЛАВИАТУРА АДМИНА
# ══════════════════════════════════════
def _admin_kb(oid: str, current: str = "new") -> InlineKeyboardMarkup:
    btns = []
    row = []
    for s, (icon, label) in STATUSES.items():
        if s == "new": continue
        row.append(InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"st:{oid}:{s}"))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(inline_keyboard=btns)

# ══════════════════════════════════════
# КОМАНДЫ
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
    await message.answer(
        f"Привет, <b>{message.from_user.first_name}</b>! 🌸\n"
        "Добро пожаловать в Флора Бутик.\n\n"
        "Нажми кнопку ниже, чтобы выбрать букет.",
        reply_markup=kb
    )

# ══════════════════════════════════════
# ПРИЁМ ЗАКАЗА (ИСПРАВЛЕНО)
# ══════════════════════════════════════
@router.message(F.web_app_data)
async def got_order(message: Message, bot: Bot):
    user = message.from_user
    raw_data = message.web_app_data.data
    log.info(f"Получены данные: {raw_data}")

    try:
        order = json.loads(raw_data)
    except Exception as e:
        log.error(f"Ошибка JSON: {e}")
        return

    oid = order.get("order_id") or f"ФЛ-{user.id}-{int(datetime.now().timestamp())}"
    total = order.get("total", 0)
    items = order.get("items", [])
    client = order.get("client", {})
    dlv_type = order.get("delivery_type", "courier")
    delivery = "Курьер" if dlv_type == "courier" else "Самовывоз"

    # Сохраняем заказ
    ORDERS[oid] = {
        "order_id": oid, "status": "new", "user_id": user.id,
        "full_name": user.full_name, "username": user.username or "",
        "client": client, "items": items, "total": total,
        "delivery": delivery, "created": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    db_save(ORDERS)

    # Текст для клиента и админа
    items_text = "\n".join([f"  🌸 {i.get('name')} x{i.get('qty')} = {i.get('price')*i.get('qty'):,} ₽" for i in items])
    
    # Ответ клиенту
    await message.answer(f"✅ <b>Заказ №{oid} принят!</b>\n\n<b>Букеты:</b>\n{items_text}\n\n💰 <b>Итого: {total:,} ₽</b>")

    # УВЕДОМЛЕНИЕ АДМИНИСТРАТОРУ
    addr_line = f"\n📍 Адрес: {client.get('addr', '—')}" if dlv_type == "courier" else ""
    admin_text = (
        f"🛒 <b>НОВЫЙ ЗАКАЗ #{oid}</b>\n\n"
        f"👤 Клиент: {user.full_name} (@{user.username or '—'})\n"
        f"📞 Тел: <code>{client.get('phone', '—')}</code>{addr_line}\n\n"
        f"<b>Состав:</b>\n{items_text}\n\n"
        f"💰 <b>Сумма: {total:,} ₽</b> ({delivery})"
    )

    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=_admin_kb(oid))
        log.info(f"✅ Уведомление успешно отправлено админу {ADMIN_ID}")
    except Exception as e:
        log.error(f"❌ Ошибка отправки админу {ADMIN_ID}: {e}")

# ══════════════════════════════════════
# СТАТУСЫ И ДРУГОЕ
# ══════════════════════════════════════
@router.callback_query(F.data.startswith("st:"))
async def cb_set_status(cb: CallbackQuery, bot: Bot):
    if cb.from_user.id != ADMIN_ID: return
    _, oid, new_status = cb.data.split(":")
    
    if oid in ORDERS:
        ORDERS[oid]["status"] = new_status
        db_save(ORDERS)
        icon, label = STATUSES[new_status]
        await cb.answer(f"Статус: {label}")
        try:
            await bot.send_message(ORDERS[oid]["user_id"], f"🌸 Статус заказа <b>#{oid}</b> изменен на: <b>{label}</b> {icon}")
        except: pass

@router.callback_query(F.data == "contacts")
async def cb_contacts(cb: CallbackQuery):
    await cb.message.answer("📞 <b>Контакты:</b>\nМенеджер: @flora_manager\nТелефон: +7 (495) 000-00-00")
    await cb.answer()

async def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
