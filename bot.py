import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


BASE_DIR = Path(__file__).resolve().parent
SCHEDULE_FILE = BASE_DIR / "schedule.json"
USERS_FILE = BASE_DIR / "users.json"


def load_json(path):
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Я бот для перевірки відключень світла.\n\n"
        "Щоб зберегти адресу, введи:\n"
        "/setaddress Київ | вул. Іленка Юрія | 1\n\n"
        "Після цього використовуй /check."
    )


async def setaddress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    address_text = message.partition(" ")[2].strip()

    parts = [part.strip() for part in address_text.split("|")]

    if len(parts) != 3 or not all(parts):
        await update.message.reply_text(
            "Неправильний формат!\n\n"
            "Приклад:\n"
            "/setaddress Київ | вул. Іленка Юрія | 1"
        )
        return

    location, street, house = parts

    if location not in ("Київ", "Київська область"):
        await update.message.reply_text(
            "Розташування має бути: Київ або Київська область."
        )
        return

    try:
        schedules = load_json(SCHEDULE_FILE)
        users = load_json(USERS_FILE)
    except (OSError, json.JSONDecodeError):
        await update.message.reply_text("Помилка читання файлів.")
        return

    address = schedules.get(location, {}).get(street, {}).get(house)

    if address is None:
        await update.message.reply_text(
            "Такої адреси поки немає в базі графіків.\n"
            "Спочатку додай її через update_schedule.py."
        )
        return

    user_id = str(update.effective_user.id)

    users[user_id] = {
        "location": location,
        "street": street,
        "house": house
    }

    save_json(USERS_FILE, users)

    await update.message.reply_text(
        "Адресу успішно збережено!\n\n"
        f"{location}, {street}, {house}\n\n"
        "Тепер просто напиши /check."
    )


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        users = load_json(USERS_FILE)
        schedules = load_json(SCHEDULE_FILE)
    except (OSError, json.JSONDecodeError):
        await update.message.reply_text("Помилка читання файлів.")
        return

    user_id = str(update.effective_user.id)

    # Якщо адресу передали прямо в команді
    address_text = update.message.text.partition(" ")[2].strip()

    if address_text:
        parts = [part.strip() for part in address_text.split("|")]

        if len(parts) != 3 or not all(parts):
            await update.message.reply_text(
                "Приклад:\n"
                "/check Київ | вул. Іленка Юрія | 1"
            )
            return

        location, street, house = parts

    else:
        # Беремо раніше збережену адресу
        saved = users.get(user_id)

        if not saved:
            await update.message.reply_text(
                "Ти ще не зберіг адресу!\n\n"
                "Введи:\n"
                "/setaddress Київ | вул. Іленка Юрія | 1"
            )
            return

        location = saved["location"]
        street = saved["street"]
        house = saved["house"]

    address = schedules.get(location, {}).get(street, {}).get(house)

    if address is None:
        await update.message.reply_text(
            "Графік для цієї адреси не знайдено."
        )
        return

    now = datetime.now(ZoneInfo("Europe/Kyiv"))

    if address["date"] != now.strftime("%Y-%m-%d"):
        await update.message.reply_text(
            "Немає актуального графіка на сьогодні."
        )
        return

    outages = address["outages"]

    if not outages:
        await update.message.reply_text(
            "У збереженому графіку немає запланованих відключень."
        )
        return

    result = "На сьогодні більше відключень за графіком немає."

    for start_time, end_time in outages:
        start_hour, start_minute = map(int, start_time.split(":"))

        start = now.replace(
            hour=start_hour,
            minute=start_minute,
            second=0,
            microsecond=0
        )

        if end_time == "24:00":
            end = now.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            ) + timedelta(days=1)
        else:
            end_hour, end_minute = map(int, end_time.split(":"))

            end = now.replace(
                hour=end_hour,
                minute=end_minute,
                second=0,
                microsecond=0
            )

        if start <= now < end:
            minutes = max(0, int((end - now).total_seconds() // 60))

            result = (
                "Зараз за графіком світла немає.\n"
                f"До відновлення: {minutes // 60} год {minutes % 60} хв"
            )
            break

        if now < start:
            minutes = max(0, int((start - now).total_seconds() // 60))

            result = (
                f"Наступне відключення о {start_time}.\n"
                f"До відключення: {minutes // 60} год {minutes % 60} хв"
            )
            break

    await update.message.reply_text(
        f"Адреса: {location}, {street}, {house}\n"
        f"Час: {now.strftime('%H:%M')}\n\n"
        f"{result}\n\n"
        "Джерело: вручну збережений графік, не онлайн-дані ДТЕК."
    )


token = os.environ.get("BOT_TOKEN")

if not token:
    raise RuntimeError("Не знайдено BOT_TOKEN")

app = ApplicationBuilder().token(token).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("setaddress", setaddress))
app.add_handler(CommandHandler("check", check))

print("Бот запущений!")
app.run_polling()