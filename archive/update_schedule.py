import json
from datetime import datetime
from pathlib import Path

FILE = Path(__file__).with_name("schedule.json")

print("=== Оновлення графіка відключень ===")
print("1. Київ")
print("2. Київська область")

choice = input("Оберіть розташування: ").strip()

if choice == "1":
    location = "Київ"
elif choice == "2":
    location = "Київська область"
else:
    print("Неправильний вибір!")
    exit()

street = input("Введіть вулицю: ").strip()
house = input("Введіть номер будинку: ").strip()
date = input("Дата графіка (РРРР-ММ-ДД): ").strip()

try:
    datetime.strptime(date, "%Y-%m-%d")
except ValueError:
    print("Неправильний формат дати!")
    exit()

print("\nВведіть проміжки відключень.")
print("Наприклад: 06:30-10:00")
print("Коли закінчите, натисніть Enter на порожньому рядку.\n")

outages = []

while True:
    interval = input("Проміжок: ").strip()

    if not interval:
        break

    try:
        start, end = [x.strip() for x in interval.split("-")]

        def to_minutes(value):
            if value == "24:00":
                return 1440

            parsed = datetime.strptime(value, "%H:%M")
            return parsed.hour * 60 + parsed.minute

        start_minutes = to_minutes(start)
        end_minutes = to_minutes(end)

        if start_minutes >= end_minutes or start_minutes == 1440:
            raise ValueError

        outages.append([start, end])

    except ValueError:
        print("Помилка! Введіть, наприклад: 06:30-10:00")

outages.sort(key=lambda item: item[0])

if FILE.exists():
    with open(FILE, "r", encoding="utf-8") as file:
        schedules = json.load(file)
else:
    schedules = {}

schedules.setdefault(location, {})
schedules[location].setdefault(street, {})

schedules[location][street][house] = {
    "date": date,
    "outages": outages
}

with open(FILE, "w", encoding="utf-8") as file:
    json.dump(schedules, file, ensure_ascii=False, indent=4)

print("\nГрафік успішно оновлено!")
print("Адреса:", location, street, house)
print("Дата:", date)
print("Відключення:", outages)