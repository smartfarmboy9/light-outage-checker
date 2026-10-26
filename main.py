import json
import re
import requests

from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
ADDRESSES_FILE = BASE_DIR / "addresses.json"

URL = "https://www.dtek-kem.com.ua/ua/shutdowns"
KYIV_TZ = ZoneInfo("Europe/Kyiv")


def get_schedules():
    response = requests.get(URL, timeout=20)
    response.raise_for_status()

    html = response.text

    match = re.search(r"DisconSchedule\.fact\s*=\s*", html)

    if not match:
        raise ValueError("Графіки ДТЕК не знайдено.")

    start = html.find("{", match.end())

    if start == -1:
        raise ValueError("Дані графіків не знайдено.")

    decoder = json.JSONDecoder()
    schedules, _ = decoder.raw_decode(html[start:])

    return schedules["data"]


def get_today_schedule(data):
    today = datetime.now(KYIV_TZ).date()

    for timestamp, groups in data.items():
        date = datetime.fromtimestamp(
            int(timestamp), KYIV_TZ
        ).date()

        if date == today:
            return groups

    return None


def find_group(street, house):
    with open(ADDRESSES_FILE, "r", encoding="utf-8") as file:
        addresses = json.load(file)

    streets = addresses.get("Київ", {})

    # Пошук без урахування регістру та зайвих пробілів
    street_normalized = " ".join(street.lower().split())
    house_normalized = house.strip().upper().replace(" ", "")

    for saved_street, houses in streets.items():
        saved_normalized = " ".join(saved_street.lower().split())

        if saved_normalized == street_normalized:
            for saved_house, group in houses.items():
                if saved_house.upper().replace(" ", "") == house_normalized:
                    return group

    return None


def calculate_outages(hours, date):
    outages = []
    outage_start = None

    for hour in range(1, 25):
        status = hours.get(str(hour))

        if status not in ("yes", "no", "first", "second"):
            raise ValueError(
                f"Невідомий стан для години {hour}: {status}"
            )

        hour_start = datetime(
            date.year, date.month, date.day,
            hour - 1, 0, tzinfo=KYIV_TZ
        )

        first_half = status in ("no", "first")
        second_half = status in ("no", "second")

        for half, is_outage in enumerate((first_half, second_half)):
            start = hour_start + timedelta(minutes=half * 30)

            if is_outage and outage_start is None:
                outage_start = start

            elif not is_outage and outage_start is not None:
                outages.append((outage_start, start))
                outage_start = None

    if outage_start is not None:
        next_day = datetime(
            date.year, date.month, date.day,
            tzinfo=KYIV_TZ
        ) + timedelta(days=1)

        outages.append((outage_start, next_day))

    return outages


def format_time(value, date):
    if value.date() > date:
        return "24:00"

    return value.strftime("%H:%M")


def format_duration(delta):
    minutes = max(0, int(delta.total_seconds() // 60))
    return f"{minutes // 60} год {minutes % 60} хв"


def show_schedule(street, house, group, outages):
    now = datetime.now(KYIV_TZ)
    today = now.date()

    print("\n" + "=" * 45)
    print("       ГРАФІК ВІДКЛЮЧЕНЬ — КИЇВ")
    print("=" * 45)

    print(f"Адреса: Київ, {street}, {house}")
    print(f"Група: {group}")
    print(f"Дата: {today:%d.%m.%Y}")
    print(f"Поточний час: {now:%H:%M}")

    print("\nГРАФІК ВІДКЛЮЧЕНЬ:")

    if not outages:
        print("За отриманим графіком відключень немає.")
        return

    for start, end in outages:
        print(
            f"  {format_time(start, today)} — "
            f"{format_time(end, today)}"
        )

    print("\n" + "-" * 45)

    for start, end in outages:
        if start <= now < end:
            print("Зараз: за графіком світла немає")
            print("Відновлення:", format_time(end, today))
            print("До відновлення:", format_duration(end - now))
            break

        if now < start:
            print("Зараз: за графіком світло є")
            print("Наступне відключення:", format_time(start, today))
            print("Відновлення:", format_time(end, today))
            print("До відключення:", format_duration(start - now))
            break
    else:
        print("На сьогодні відключення за графіком завершилися.")

    print("\nДжерело графіка: ДТЕК")
    print("Група визначена за локальною базою addresses.json.")
    print("Увага: фактичні відключення можуть відрізнятися.")


def main():
    print("=" * 45)
    print("       ПЕРЕВІРКА ВІДКЛЮЧЕНЬ СВІТЛА")
    print("                  КИЇВ")
    print("=" * 45)

    try:
        street = input("\nВведіть вулицю: ").strip()
        house = input("Введіть номер будинку: ").strip()

        if not street or not house:
            print("Помилка: введіть вулицю та номер будинку.")
            return

        group = find_group(street, house)

        if not group:
            print("\nАдресу не знайдено в локальній базі.")
            print("Автоматичний пошук усіх адрес Києва ще не реалізований.")
            return

        print(f"\nЗнайдена група: {group}")
        print("Завантаження графіка ДТЕК...")

        data = get_schedules()
        today_schedule = get_today_schedule(data)

        if not today_schedule:
            print("Немає актуального графіка на сьогодні.")
            return

        hours = today_schedule.get(group)

        if hours is None:
            print("Графік для цієї групи не знайдено.")
            return

        today = datetime.now(KYIV_TZ).date()
        outages = calculate_outages(hours, today)

        show_schedule(street, house, group, outages)

    except FileNotFoundError:
        print("Помилка: файл addresses.json не знайдено.")

    except json.JSONDecodeError:
        print("Помилка: неправильний формат JSON.")

    except requests.RequestException as error:
        print("Помилка підключення до ДТЕК:", error)

    except (ValueError, KeyError, TypeError) as error:
        print("Помилка обробки даних:", error)


if __name__ == "__main__":
    main()