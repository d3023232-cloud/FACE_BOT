# 🤖 Face Analyzer Bot — Деплой

## 1. Переменные окружения (ENV)

Все настройки бота берутся из переменных окружения. **НЕ редактируйте код!**

### Обязательные:
| Переменная | Описание | Где взять |
|-----------|----------|-----------|
| `BOT_TOKEN` | Токен бота | @BotFather → /newbot |
| `GITHUB_TOKEN` | GitHub PAT | github.com/settings/tokens |
| `ADMIN_ID` | Ваш Telegram ID | @userinfobot |

### Опциональные:
| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `PRICE_STARS` | 10 | Стоимость анализа в ⭐ |
| `FREE_ANALYSES` | 1 | Бесплатных анализов |

---

## 2. Локальный запуск

```bash
# 1. Клонируйте проект
cd face-bot

# 2. Создайте .env файл
cp .env.example .env
# Отредактируйте .env своими значениями

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Запустите (Linux/Mac)
export $(cat .env | xargs) && python bot.py

# Или (Windows PowerShell)
Get-Content .env | ForEach-Object { if ($_ -match "^(.*?)=(.*)$") { Set-Item -Path "env:$($matches[1])" -Value $matches[2] } }
python bot.py
```

---

## 3. Деплой на хостинг (Bot-Host / PythonAnywhere / VPS)

### Вариант A: Bot-Host (рекомендуется)
1. Загрузите файлы `bot.py`, `requirements.txt`
2. В панели управления найдите раздел **Environment Variables**
3. Добавьте переменные:
   - `BOT_TOKEN` = ваш токен
   - `GITHUB_TOKEN` = ваш GitHub токен
   - `ADMIN_ID` = ваш ID
   - `PRICE_STARS` = 10
   - `FREE_ANALYSES` = 1
4. Укажите `requirements.txt` как файл зависимостей
5. Запустите `bot.py`

### Вариант B: VPS (Ubuntu)
```bash
# Установка
sudo apt update && sudo apt install python3-pip -y
pip3 install -r requirements.txt

# Запуск с env
BOT_TOKEN="..." GITHUB_TOKEN="..." ADMIN_ID="123" python3 bot.py

# Или через systemd (автозапуск)
sudo nano /etc/systemd/system/facebot.service
```

**Содержимое facebot.service:**
```ini
[Unit]
Description=Face Analyzer Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/face-bot
Environment="BOT_TOKEN=your_token"
Environment="GITHUB_TOKEN=your_token"
Environment="ADMIN_ID=123456789"
Environment="PRICE_STARS=10"
Environment="FREE_ANALYSES=1"
ExecStart=/usr/bin/python3 /root/face-bot/bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable facebot
sudo systemctl start facebot
sudo systemctl status facebot
```

---

## 4. Получение токенов

### GitHub Token
1. https://github.com/settings/tokens
2. Generate new token (classic)
3. Выберите scope: `read:packages`
4. Скопируйте токен (покажется один раз!)

### Telegram Bot Token
1. Напишите @BotFather
2. /newbot → придумайте имя
3. Скопируйте токен

### Telegram ID
1. Напишите @userinfobot
2. Он пришлёт ваш ID

---

## 5. Файлы проекта

```
face-bot/
├── bot.py              # Основной файл бота
├── requirements.txt    # Зависимости
├── .env.example        # Шаблон переменных
├── face_bot.db         # База данных (создаётся автоматически)
└── README.md           # Этот файл
```

---

## 6. Лимиты GitHub Models (бесплатно)

| Модель | Лимит |
|--------|-------|
| GPT-4o-mini | ~1,000 запросов/день |
| GPT-4o | ~150 запросов/день |

С защитой (2 запроса на фото) → ~500 анализов/день.

---

Удачного запуска! 🚀
