import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Я бот для перевірки відключень світла.\n\n"
        "Для перевірки введи:\n"
        "/check Київ | вул. Іленка Юрія | 1"
    )


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text

    address_text = message.replace("/check", "", 1).strip()
    parts = [part.strip() for part in address_text.split("|")]

    if len(parts) != 3:
        await update.message.reply_text(
            "Введи адресу у форматі:\n"
            "/check Київ | вул. Іленка Юрія | 1"
        )
        return

    location, street, house = parts

    try:
        with open("schedule.json", "r", encoding="utf-8") as file:
            schedules = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        await update.message.reply_text("Не вдалося прочитати schedule.json.")
        return

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
            minutes = int((end - now).total_seconds() // 60)
            result = (
                "Зараз за графіком світла немає.\n"
                f"До відновлення: {minutes // 60} год {minutes % 60} хв"
            )
            break

        if now < start:
            minutes = int((start - now).total_seconds() // 60)
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
app.add_handler(CommandHandler("check", check))

print("Бот запущений!")
app.run_polling()