import asyncio
import logging
import os
import random
import re
import base64
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from openai import AsyncOpenAI
import aiosqlite

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
PRICE_STARS = int(os.getenv("PRICE_STARS", "10"))
FREE_ANALYSES = int(os.getenv("FREE_ANALYSES", "1"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set in environment")
if not GITHUB_TOKEN:
    raise ValueError("GITHUB_TOKEN not set in environment")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID not set in environment")

ADMIN_ID = int(ADMIN_ID)
DB_PATH = "/app/data/face_bot.db"

os.makedirs("/app/data", exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN
)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                free_balance INTEGER DEFAULT 0,
                stars_balance INTEGER DEFAULT 0,
                total_analyses INTEGER DEFAULT 0,
                joined_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                eyes INTEGER,
                nose INTEGER,
                skin INTEGER,
                cheekbones INTEGER,
                lips INTEGER,
                eyebrows INTEGER,
                hair INTEGER,
                symmetry INTEGER,
                total REAL,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                created_at TEXT
            )
        """)
        await db.commit()

async def get_or_create_user(user_id, username=None, first_name=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute(
                    "INSERT INTO users (user_id, username, first_name, free_balance, joined_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, first_name, FREE_ANALYSES, datetime.now().isoformat())
                )
                await db.commit()
                return {"user_id": user_id, "free_balance": FREE_ANALYSES, "stars_balance": 0, "total_analyses": 0}
            return {
                "user_id": row[0], "username": row[1], "first_name": row[2],
                "free_balance": row[3], "stars_balance": row[4], "total_analyses": row[5]
            }

async def use_analysis(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT free_balance, stars_balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            free_balance, stars = row[0], row[1]
            if free_balance > 0:
                await db.execute(
                    "UPDATE users SET free_balance = free_balance - 1, total_analyses = total_analyses + 1 WHERE user_id = ?",
                    (user_id,)
                )
            elif stars >= PRICE_STARS:
                await db.execute(
                    "UPDATE users SET stars_balance = stars_balance - ?, total_analyses = total_analyses + 1 WHERE user_id = ?",
                    (PRICE_STARS, user_id)
                )
            else:
                return False
            await db.commit()
            return True

async def add_stars(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET stars_balance = stars_balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def remove_stars(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET stars_balance = MAX(0, stars_balance - ?) WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def add_free(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET free_balance = free_balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def remove_free(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET free_balance = MAX(0, free_balance - ?) WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def save_analysis(user_id, data):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO analyses
            (user_id, eyes, nose, skin, cheekbones, lips, eyebrows, hair, symmetry, total, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, data["eyes"], data["nose"], data["skin"], data["cheekbones"],
            data["lips"], data["eyebrows"], data["hair"], data["symmetry"],
            data["total"], datetime.now().isoformat()
        ))
        await db.commit()

async def save_payment(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (user_id, amount, created_at) VALUES (?, ?, ?)",
            (user_id, amount, datetime.now().isoformat())
        )
        await db.commit()

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        async with db.execute("SELECT COUNT(*) as total FROM analyses") as c:
            total_analyses = (await c.fetchone())["total"]

        async with db.execute("SELECT COUNT(*) as today FROM analyses WHERE date(created_at) = ?", (today,)) as c:
            today_analyses = (await c.fetchone())["today"]

        async with db.execute("SELECT COUNT(*) as week FROM analyses WHERE date(created_at) >= ?", (week_ago,)) as c:
            week_analyses = (await c.fetchone())["week"]

        async with db.execute("SELECT COUNT(*) as month FROM analyses WHERE date(created_at) >= ?", (month_ago,)) as c:
            month_analyses = (await c.fetchone())["month"]

        async with db.execute("SELECT SUM(amount) as total FROM payments") as c:
            total_purchased = (await c.fetchone())["total"] or 0

        async with db.execute("SELECT COUNT(DISTINCT user_id) as active FROM analyses WHERE date(created_at) >= ?", (week_ago,)) as c:
            active_users = (await c.fetchone())["active"]

        async with db.execute("SELECT COUNT(*) as total_users FROM users") as c:
            total_users = (await c.fetchone())["total_users"]

        return {
            "total_analyses": total_analyses,
            "today_analyses": today_analyses,
            "week_analyses": week_analyses,
            "month_analyses": month_analyses,
            "total_purchased": total_purchased,
            "active_users": active_users,
            "total_users": total_users
        }

async def get_user_by_id(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            if row:
                return dict(row)
            return None

async def get_user_by_username(username):
    clean = username.lstrip("@").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE LOWER(username) = ?", (clean,)) as c:
            row = await c.fetchone()
            if row:
                return dict(row)
            return None

async def resolve_user(text):
    text = text.strip()
    if text.startswith("@"):
        return await get_user_by_username(text)
    if text.isdigit():
        return await get_user_by_id(int(text))
    return await get_user_by_username(text)

async def check_human_face(image_bytes):
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Ты детектор лиц. Ответь ТОЛЬКО одним словом: ДА если на фото есть реальное человеческое лицо. Ответь НЕТ если на фото нет лица, или это мем, рисунок, животное, предмет, пейзаж, аниме, фильтр, маска, фото с несколькими лицами, или лицо слишком размыто/маленькое."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Есть ли на этом фото одно реальное человеческое лицо?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "low"}
                    }
                ]
            }
        ],
        max_tokens=10,
        temperature=0
    )
    answer = response.choices[0].message.content.strip().upper()
    return "ДА" in answer

async def analyze_face(image_bytes):
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """Ты эксперт-эстетист. Оцени черты лица строго по формату:

👁 ГЛАЗА: X/100
👃 НОС: X/100
✨ КОЖА: X/100
🦴 СКУЛЫ: X/100
💋 ГУБЫ: X/100
🖤 БРОВИ: X/100
💇 ПРИЧЁСКА: X/100
⚖️ СИММЕТРИЯ: X/100

━━━━━━━━━━━━━━━
⭐ ОБЩИЙ БАЛЛ: X.X/10
━━━━━━━━━━━━━━━

Без комментариев. Только оценки."""
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Оцени:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}
                    }
                ]
            }
        ],
        max_tokens=500,
        temperature=0.3
    )
    return response.choices[0].message.content

def parse_analysis(text):
    result = {
        "eyes": 0, "nose": 0, "skin": 0, "cheekbones": 0,
        "lips": 0, "eyebrows": 0, "hair": 0, "symmetry": 0, "total": 0.0
    }
    patterns = {
        "eyes": r"👁.*?ГЛАЗА[:\s]+(\d+)",
        "nose": r"👃.*?НОС[:\s]+(\d+)",
        "skin": r"✨.*?КОЖА[:\s]+(\d+)",
        "cheekbones": r"🦴.*?СКУЛЫ[:\s]+(\d+)",
        "lips": r"💋.*?ГУБЫ[:\s]+(\d+)",
        "eyebrows": r"🖤.*?БРОВИ[:\s]+(\d+)",
        "hair": r"💇.*?ПРИЧ[ЕЁ]СКА[:\s]+(\d+)",
        "symmetry": r"⚖️.*?СИММЕТРИЯ[:\s]+(\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result[key] = int(match.group(1))
    total_match = re.search(r"ОБЩИЙ БАЛЛ[:\s]+(\d+\.\d+|\d+)", text)
    if total_match:
        result["total"] = float(total_match.group(1))
    return result

class AdminStates(StatesGroup):
    waiting_user_id = State()
    waiting_stars_amount = State()

def main_menu(user_id):
    buttons = [
        [InlineKeyboardButton(text="⭐ Купить звёзды", callback_data="buy_menu")],
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def buy_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 10 звёзд", callback_data="buy_10")],
        [InlineKeyboardButton(text="⭐ 50 звёзд", callback_data="buy_50")],
        [InlineKeyboardButton(text="⭐ 100 звёзд", callback_data="buy_100")],
        [InlineKeyboardButton(text="✏️ Свой вариант", callback_data="buy_custom")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ])

def admin_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="⭐ Выдать звёзды", callback_data="admin_give_stars")],
        [InlineKeyboardButton(text="⭐ Забрать звёзды", callback_data="admin_take_stars")],
        [InlineKeyboardButton(text="🎁 Выдать бесплатные", callback_data="admin_give_free")],
        [InlineKeyboardButton(text="🎁 Забрать бесплатные", callback_data="admin_take_free")],
        [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin_find")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")],
    ])

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = (
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        f"📸 Я бот для анализа черт лица.\n"
        f"Отправь фотку в любое время — я сделаю по ней анализ.\n\n"
        f"🎁 Бесплатных анализов: <b>{user['free_balance']}</b>\n"
        f"⭐ Баланс: {user['stars_balance']} | Анализ: {PRICE_STARS}⭐"
    )
    await message.answer(text, reply_markup=main_menu(message.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user.id)
    text = (
        f"👋 Главное меню\n\n"
        f"🎁 Бесплатных: <b>{user['free_balance']}</b>\n"
        f"⭐ Баланс: {user['stars_balance']} | Анализ: {PRICE_STARS}⭐"
    )
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "buy_menu")
async def cb_buy_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "⭐ <b>Выберите количество звёзд:</b>",
        reply_markup=buy_menu_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: CallbackQuery):
    data = callback.data.replace("buy_", "")
    if data == "custom":
        await callback.message.edit_text(
            "✏️ Введите количество звёзд для покупки (число):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_menu")]
            ])
        )
        await callback.answer()
        return

    amount = int(data)
    await callback.message.answer_invoice(
        title=f"⭐ {amount} звёзд",
        description=f"Покупка {amount} звёзд для анализа лица",
        payload=f"stars_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{amount} звёзд", amount=amount)],
        provider_token=""
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    amount = message.successful_payment.total_amount
    await save_payment(message.from_user.id, amount)
    await add_stars(message.from_user.id, amount)
    await message.answer(f"✅ Зачислено {amount} ⭐!")

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа")
        return
    await message.answer(
        "🔧 <b>Админ-панель</b>",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    stats = await get_stats()
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей всего: <b>{stats['total_users']}</b>\n"
        f"🔥 Активных за неделю: <b>{stats['active_users']}</b>\n\n"
        f"📸 Фото обработано:\n"
        f"  • За сегодня: <b>{stats['today_analyses']}</b>\n"
        f"  • За неделю: <b>{stats['week_analyses']}</b>\n"
        f"  • За месяц: <b>{stats['month_analyses']}</b>\n"
        f"  • За всё время: <b>{stats['total_analyses']}</b>\n\n"
        f"💰 Куплено звёзд всего: <b>{stats['total_purchased']}</b> ⭐"
    )
    await callback.message.edit_text(text, reply_markup=admin_menu_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_give_stars")
async def cb_admin_give_stars(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(action="give_stars")
    await callback.message.edit_text(
        "⭐ <b>Выдать звёзды</b>\n\nВведите ID пользователя или @username:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_take_stars")
async def cb_admin_take_stars(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(action="take_stars")
    await callback.message.edit_text(
        "⭐ <b>Забрать звёзды</b>\n\nВведите ID пользователя или @username:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_give_free")
async def cb_admin_give_free(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(action="give_free")
    await callback.message.edit_text(
        "🎁 <b>Выдать бесплатные анализы</b>\n\nВведите ID пользователя или @username:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_take_free")
async def cb_admin_take_free(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(action="take_free")
    await callback.message.edit_text(
        "🎁 <b>Забрать бесплатные анализы</b>\n\nВведите ID пользователя или @username:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_find")
async def cb_admin_find(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(action="find")
    await callback.message.edit_text(
        "🔍 <b>Найти пользователя</b>\n\nВведите ID или @username:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "🔧 <b>Админ-панель</b>",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(AdminStates.waiting_user_id)
async def process_user_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    text = message.text.strip()
    user = await resolve_user(text)

    if not user:
        await message.answer("❌ Пользователь не найден. Проверьте ID или @username.")
        return

    data = await state.get_data()
    action = data.get("action")

    if action == "find":
        await message.answer(
            f"👤 <b>Пользователь</b>\n\n"
            f"🆔 ID: <code>{user['user_id']}</code>\n"
            f"👤 Имя: {user.get('first_name', '—')}\n"
            f"🔗 Юзернейм: @{user.get('username', '—')}\n"
            f"🎁 Бесплатных: {user['free_balance']}\n"
            f"⭐ Баланс: {user['stars_balance']}\n"
            f"📊 Всего анализов: {user['total_analyses']}\n"
            f"📅 Регистрация: {user.get('joined_at', '—')[:10]}",
            reply_markup=admin_menu_kb(),
            parse_mode="HTML"
        )
        await state.clear()
        return

    await state.update_data(user_id=user["user_id"], username=user.get("username"))
    await state.set_state(AdminStates.waiting_stars_amount)

    action_text = {
        "give_stars": "сколько звёзд выдать",
        "take_stars": "сколько звёзд забрать",
        "give_free": "сколько бесплатных анализов выдать",
        "take_free": "сколько бесплатных анализов забрать"
    }

    await message.answer(
        f"Пользователь: <b>@{user.get('username') or user['user_id']}</b>\n\n"
        f"Введите число — {action_text.get(action, 'количество')}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_menu")]
        ]),
        parse_mode="HTML"
    )

@dp.message(AdminStates.waiting_stars_amount)
async def process_amount(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        amount = int(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Введите положительное число")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return

    data = await state.get_data()
    action = data.get("action")
    user_id = data.get("user_id")
    username = data.get("username")
    name = f"@{username}" if username else f"ID {user_id}"

    if action == "give_stars":
        await add_stars(user_id, amount)
        await message.answer(f"✅ Выдано {amount} ⭐ пользователю {name}")
    elif action == "take_stars":
        await remove_stars(user_id, amount)
        await message.answer(f"✅ Забрано {amount} ⭐ у пользователя {name}")
    elif action == "give_free":
        await add_free(user_id, amount)
        await message.answer(f"✅ Выдано {amount} бесплатных анализов пользователю {name}")
    elif action == "take_free":
        await remove_free(user_id, amount)
        await message.answer(f"✅ Забрано {amount} бесплатных анализов у пользователя {name}")

    await state.clear()
    await message.answer("🔧 Админ-панель", reply_markup=admin_menu_kb())

ERROR_MESSAGES = [
    "🚫 На фото не обнаружено человеческое лицо. Попробуй другое фото — чёткое, в хорошем свете, лицом в камеру.",
    "🚫 Не вижу лицо. Возможно, это не фото человека, или лицо слишком далеко/размыто. Попробуй ещё раз!",
    "🚫 Ошибка: на фото должно быть одно реальное человеческое лицо. Без масок, фильтров и мемов 😄",
    "🚫 Хм, это точно фото лица? Я не могу найти человеческое лицо на этом изображении. Попробуй другое!",
    "🚫 Лицо не найдено. Убедись, что на фото одно лицо, без очков-солнцезащитных, масок и сильных фильтров."
]

@dp.message(F.photo)
async def handle_photo(message: Message):
    user = await get_or_create_user(message.from_user.id)

    if user["free_balance"] <= 0 and user["stars_balance"] < PRICE_STARS:
        await message.answer(
            f"❌ Анализ недоступен\n\n"
            f"Нужно: {PRICE_STARS}⭐ | У тебя: {user['stars_balance']}⭐\n"
            f"Купить: /start",
            reply_markup=main_menu(message.from_user.id)
        )
        return

    loading = await message.answer("🔍 Проверяю фото...")

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        image_bytes = await bot.download_file(file.file_path)
        image_data = image_bytes.read()

        is_human = await check_human_face(image_data)

        if not is_human:
            await loading.edit_text(random.choice(ERROR_MESSAGES))
            return

        await loading.edit_text("🔍 Анализирую черты лица...")

        result = await analyze_face(image_data)
        parsed = parse_analysis(result)
        await save_analysis(message.from_user.id, parsed)

        success = await use_analysis(message.from_user.id)
        if not success:
            await loading.edit_text("❌ Ошибка списания. Попробуй снова.")
            return

        user = await get_or_create_user(message.from_user.id)

        await loading.edit_text(
            f"{result}\n\n"
            f"📊 Бесплатных: {user['free_balance']} | ⭐ {user['stars_balance']}"
        )

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await loading.edit_text("❌ Ошибка анализа. Попробуй другое фото.")

async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
