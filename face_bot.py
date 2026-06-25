import asyncio
import logging
import re
import base64
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command
from openai import AsyncOpenAI
import aiosqlite

BOT_TOKEN = "YOUR_BOT_TOKEN"
GITHUB_TOKEN = "YOUR_GITHUB_TOKEN"
ADMIN_ID = 123456789
PRICE_STARS = 10
FREE_ANALYSES = 1

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN
)

async def init_db():
    async with aiosqlite.connect("face_bot.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                free_used INTEGER DEFAULT 0,
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
        await db.commit()

async def get_or_create_user(user_id, username=None, first_name=None):
    async with aiosqlite.connect("face_bot.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute(
                    "INSERT INTO users (user_id, username, first_name, free_used, joined_at) VALUES (?, ?, ?, 0, ?)",
                    (user_id, username, first_name, datetime.now().isoformat())
                )
                await db.commit()
                return {"user_id": user_id, "free_used": 0, "stars_balance": 0, "total_analyses": 0}
            return {
                "user_id": row[0], "username": row[1], "first_name": row[2],
                "free_used": row[3], "stars_balance": row[4], "total_analyses": row[5]
            }

async def use_analysis(user_id):
    async with aiosqlite.connect("face_bot.db") as db:
        async with db.execute("SELECT free_used, stars_balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            free_used, stars = row[0], row[1]
            if free_used < FREE_ANALYSES:
                await db.execute(
                    "UPDATE users SET free_used = free_used + 1, total_analyses = total_analyses + 1 WHERE user_id = ?",
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
    async with aiosqlite.connect("face_bot.db") as db:
        await db.execute(
            "UPDATE users SET stars_balance = stars_balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def save_analysis(user_id, data):
    async with aiosqlite.connect("face_bot.db") as db:
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

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    free_left = FREE_ANALYSES - user["free_used"]
    await message.answer(
        f"👋 Привет, <b>{message.from_user.first_name}</b>!

"
        f"📸 Отправь фото лица — я оценю 8 параметров:
"
        f"👁 Глаза • 👃 Нос • ✨ Кожа • 🦴 Скулы
"
        f"💋 Губы • 🖤 Брови • 💇 Причёска • ⚖️ Симметрия

"
        f"🎁 Бесплатных анализов: <b>{max(0, free_left)}</b>
"
        f"⭐ Баланс: {user['stars_balance']} | Анализ: {PRICE_STARS}⭐

"
        f"Купить звёзды: /buy",
        parse_mode="HTML"
    )

@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user = await get_or_create_user(message.from_user.id)
    free_left = max(0, FREE_ANALYSES - user["free_used"])
    await message.answer(
        f"👤 <b>Профиль</b>

"
        f"🎁 Бесплатных: {free_left}
"
        f"⭐ Баланс: {user['stars_balance']}
"
        f"📊 Всего анализов: {user['total_analyses']}",
        parse_mode="HTML"
    )

@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    await message.answer_invoice(
        title="⭐ Звёзды",
        description="Покупка звёзд для анализа лица",
        payload="stars_payment",
        currency="XTR",
        prices=[LabeledPrice(label="50 звёзд", amount=50)],
        provider_token=""
    )

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    amount = message.successful_payment.total_amount
    await add_stars(message.from_user.id, amount)
    await message.answer(f"✅ Зачислено {amount} ⭐!")

ERROR_MESSAGES = [
    "🚫 На фото не обнаружено человеческое лицо. Попробуй другое фото — чёткое, в хорошем свете, лицом в камеру.",
    "🚫 Не вижу лицо. Возможно, это не фото человека, или лицо слишком далеко/размыто. Попробуй ещё раз!",
    "🚫 Ошибка: на фото должно быть одно реальное человеческое лицо. Без масок, фильтров и мемов 😄",
    "🚫 Хм, это точно фото лица? Я не могу найти человеческое лицо на этом изображении. Попробуй другое!",
    "🚫 Лицо не найдено. Убедись, что на фото одно лицо, без очков-солнцезащитных, масок и сильных фильтров."
]

import random

@dp.message(F.photo)
async def handle_photo(message: Message):
    user = await get_or_create_user(message.from_user.id)
    free_left = max(0, FREE_ANALYSES - user["free_used"])

    if free_left <= 0 and user["stars_balance"] < PRICE_STARS:
        await message.answer(
            f"❌ Анализ недоступен

"
            f"Нужно: {PRICE_STARS}⭐ | У тебя: {user['stars_balance']}⭐
"
            f"Купить: /buy"
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
        free_left = max(0, FREE_ANALYSES - user["free_used"])

        await loading.edit_text(
            f"{result}

"
            f"📊 Бесплатных: {free_left} | ⭐ {user['stars_balance']}"
        )

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await loading.edit_text("❌ Ошибка анализа. Попробуй другое фото.")

@dp.message(F.text)
async def handle_text(message: Message):
    await message.answer(
        "📸 Отправь фото <b>лица</b> для анализа

"
        "/start — меню
"
        "/profile — профиль
"
        "/buy — купить звёзды",
        parse_mode="HTML"
    )

async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
