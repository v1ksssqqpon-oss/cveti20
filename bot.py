import os
import json
import sqlite3
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ContentType
from aiogram.filters import CommandStart
from aiogram.types.web_app_info import WebAppInfo
from aiogram.client.default import DefaultBotProperties
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
ADMIN_ID = os.getenv("ADMIN_ID")
# Реквизиты для оплаты
PAYMENT_DETAILS = "Сбербанк / Т-Банк: 0000 0000 0000 0000 (Иван И.)"

if not all([BOT_TOKEN, WEBAPP_URL, ADMIN_ID]):
    raise ValueError("ОШИБКА: Проверь .env! Нужны BOT_TOKEN, WEBAPP_URL и ADMIN_ID")

# --- База Данных ---
def init_db():
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            items TEXT,
            total INTEGER,
            delivery_type TEXT,
            client_name TEXT,
            phone TEXT,
            address TEXT,
            time TEXT,
            comment TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- FSM (Состояния) ---
class AdminState(StatesGroup):
    waiting_for_comment = State()

class OrderCB(CallbackData, prefix="order"):
    action: str
    order_id: int

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Открыть Каталог", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer("<b>MAISON DES FLEURS</b>\n\nСоберите свой идеальный букет.", reply_markup=markup)

# --- 1. Получение заказа из WebApp ---
@router.message(F.web_app_data)
async def process_web_app_data(message: Message, bot: Bot):
    try:
        data = json.loads(message.web_app_data.data)
        
        # Сохраняем расширенный заказ
        conn = sqlite3.connect("shop.db")
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO orders (user_id, username, items, total, delivery_type, client_name, phone, address, time, comment, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            message.from_user.id, message.from_user.username, 
            json.dumps(data['items'], ensure_ascii=False), data['total'],
            data['delivery_type'], data['name'], data['phone'], 
            data.get('address', ''), data['time'], data.get('comment', ''), "new"
        ))
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Формируем список товаров для текста
        items_text = "\n".join([f"▫️ {item['name']} x{item['qty']} ({item['price'] * item['qty']} ₽)" for item in data['items']])

        # Ответ клиенту
        client_text = f"🧾 <b>Заказ №{order_id} оформлен!</b>\n\n{items_text}\n\n💳 <b>Итого:</b> {data['total']} ₽\n⏳ <i>Менеджер проверяет наличие. Ожидайте подтверждения...</i>"
        await message.answer(client_text)

        # Уведомление админу
        admin_text = (
            f"🚨 <b>НОВЫЙ ЗАКАЗ №{order_id}</b>\n\n"
            f"👤 <b>Клиент:</b> {data['name']} (@{message.from_user.username})\n"
            f"📞 <b>Телефон:</b> {data['phone']}\n"
            f"🚚 <b>Тип:</b> {data['delivery_type']}\n"
            f"📍 <b>Адрес/Время:</b> {data.get('address', 'Самовывоз')} | {data['time']}\n"
            f"💬 <b>Коммент:</b> {data.get('comment', 'Нет')}\n\n"
            f"<b>Корзина:</b>\n{items_text}\n\n"
            f"💰 <b>Сумма:</b> {data['total']} ₽"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Одобрить", callback_data=OrderCB(action="approve", order_id=order_id))
        builder.button(text="❌ Отклонить", callback_data=OrderCB(action="reject", order_id=order_id))
        
        await bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"Ошибка заказа: {e}")

# --- 2. Админ нажимает Одобрить/Отклонить ---
@router.callback_query(OrderCB.filter())
async def admin_process_order(call: CallbackQuery, callback_data: OrderCB, state: FSMContext):
    if str(call.from_user.id) != str(ADMIN_ID):
        return await call.answer("Нет доступа", show_alert=True)

    await state.update_data(order_id=callback_data.order_id, action=callback_data.action)
    await state.set_state(AdminState.waiting_for_comment)
    
    action_ru = "одобрения" if callback_data.action == "approve" else "отклонения"
    await call.message.answer(f"✍️ Введите комментарий для клиента (причина {action_ru} или уточнение):")
    await call.answer()

# --- 3. Админ пишет комментарий, бот отправляет реквизиты клиенту ---
@router.message(AdminState.waiting_for_comment)
async def admin_comment_received(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data['order_id']
    action = data['action']
    admin_comment = message.text

    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, total FROM orders WHERE id = ?", (order_id,))
    order_data = cursor.fetchone()
    
    if not order_data:
        await message.answer("Ошибка: Заказ не найден.")
        return await state.clear()
        
    user_id, total = order_data

    if action == "approve":
        cursor.execute("UPDATE orders SET status = 'awaiting_receipt' WHERE id = ?", (order_id,))
        client_msg = (
            f"✅ <b>Заказ №{order_id} одобрен!</b>\n\n"
            f"💬 <b>Комментарий менеджера:</b> <i>{admin_comment}</i>\n\n"
            f"💳 К оплате: <b>{total} ₽</b>\n"
            f"🏦 Реквизиты: <code>{PAYMENT_DETAILS}</code>\n\n"
            f"📸 <b>Пожалуйста, отправьте фото чека об оплате прямо в этот чат.</b>"
        )
        await message.answer(f"Заказ №{order_id} одобрен. Ждем чек от клиента.")
    else:
        cursor.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        client_msg = (
            f"❌ <b>Заказ №{order_id} отклонен.</b>\n\n"
            f"💬 <b>Причина:</b> <i>{admin_comment}</i>"
        )
        await message.answer(f"Заказ №{order_id} отклонен.")

    conn.commit()
    conn.close()
    await state.clear()

    try:
        await bot.send_message(chat_id=user_id, text=client_msg)
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение клиенту {user_id}")

# --- 4. Клиент отправляет фото (чек) ---
@router.message(F.photo)
async def process_receipt(message: Message, bot: Bot):
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    # Ищем заказ клиента, который ждет оплаты
    cursor.execute("SELECT id FROM orders WHERE user_id = ? AND status = 'awaiting_receipt'", (message.from_user.id,))
    order = cursor.fetchone()
    
    if order:
        order_id = order[0]
        cursor.execute("UPDATE orders SET status = 'paid_check_pending' WHERE id = ?", (order_id,))
        conn.commit()
        
        await message.answer("✅ Чек получен! Менеджер скоро проверит оплату и свяжется с вами.")
        
        # Пересылаем чек админу
        await bot.send_photo(
            chat_id=ADMIN_ID, 
            photo=message.photo[-1].file_id, 
            caption=f"💰 <b>ЧЕК ПО ЗАКАЗУ №{order_id}</b>\nОт: @{message.from_user.username}\n\n<i>Для уточнения деталей напишите клиенту в личные сообщения.</i>"
        )
    conn.close()

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
