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


def normalize_street(value):
    value = value.casefold()
    value = value.replace("’", "'").replace("ʼ", "'")
    value = re.sub(r"\s+", " ", value).strip()

    prefixes = (
        "вул.", "вулиця",
        "просп.", "проспект",
        "пров.", "провулок",
        "бул.", "бульвар",
        "пл.", "площа",
        "шосе",
    )

    for prefix in prefixes:
        if value.startswith(prefix + " "):
            value = value[len(prefix):].strip()
            break

    return value


def normalize_house(value):
    value = value.casefold()
    value = value.replace(" ", "")
    value = value.replace("-", "")
    value = value.replace("/", "")
    return value


def load_addresses():
    with open(ADDRESSES_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    if "Київ" in data and isinstance(data["Київ"], dict):
        return data["Київ"]

    return data


def find_groups(street, house):
    addresses = load_addresses()

    street_query = normalize_street(street)
    house_query = normalize_house(house)

    matches = []

    for saved_street, houses in addresses.items():
        if normalize_street(saved_street) == street_query:
            matches.append((saved_street, houses))

    if not matches:
        suggestions = [
            name for name in addresses
            if street_query in normalize_street(name)
        ][:10]

        print("\nВулицю не знайдено.")

        if suggestions:
            print("Можливо, ви мали на увазі:")
            for name in suggestions:
                print(" -", name)

        return None

    if len(matches) > 1:
        print("\nЗнайдено декілька вулиць:")
        for name, _ in matches:
            print(" -", name)

        print("Введіть повну назву з типом вулиці.")
        return None

    saved_street, houses = matches[0]

    for saved_house, info in houses.items():
        if normalize_house(saved_house) != house_query:
            continue

        if isinstance(info, dict):
            groups = info.get("sub_type_reason", [])

        elif isinstance(info, str):
            groups = [info]

        elif isinstance(info, list):
            groups = info

        else:
            groups = []

        if isinstance(groups, str):
            groups = [groups]

        groups = [
            group for group in groups
            if isinstance(group, str) and group.startswith("GPV")
        ]

        return saved_street, saved_house, list(dict.fromkeys(groups))

    print(f"\nБудинок {house} не знайдено на вулиці {saved_street}.")
    return None


def get_schedules():
    response = requests.get(
        URL,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    html = response.text

    match = re.search(
        r"DisconSchedul(?:e|&#x65;)\.(?:f|&#x66;)act\s*=\s*",
        html
    )

    if not match:
        raise ValueError("Графіки ДТЕК не знайдено на сторінці.")

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
            int(timestamp),
            KYIV_TZ
        ).date()

        if date == today:
            return groups

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
            date.year,
            date.month,
            date.day,
            hour - 1,
            0,
            tzinfo=KYIV_TZ
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
            date.year,
            date.month,
            date.day,
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

    print("\n" + "=" * 50)
    print("ГРАФІК ВІДКЛЮЧЕНЬ - КИЇВ")
    print("=" * 50)

    print(f"Адреса: Київ, {street}, {house}")
    print(f"Група: {group}")
    print(f"Дата: {today:%d.%m.%Y}")
    print(f"Поточний час: {now:%H:%M}")

    print("\nГРАФІК ВІДКЛЮЧЕНЬ:")

    if not outages:
        print("За отриманим графіком відключень немає.")
        print("Увага: фактична ситуація може відрізнятися.")
        return

    for start, end in outages:
        print(
            f"  {format_time(start, today)} - "
            f"{format_time(end, today)}"
        )

    print("\n" + "-" * 50)

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
    print("Фактичні відключення можуть відрізнятися.")


def main():
    print("=" * 50)
    print("ПЕРЕВІРКА ВІДКЛЮЧЕНЬ СВІТЛА - КИЇВ")
    print("=" * 50)

    try:
        street = input("\nВведіть вулицю: ").strip()
        house = input("Введіть номер будинку: ").strip()

        if not street or not house:
            print("Помилка: введіть вулицю та номер будинку.")
            return

        result = find_groups(street, house)

        if result is None:
            return

        saved_street, saved_house, groups = result

        if not groups:
            print("\nДля цієї адреси групу відключень не визначено.")
            return

        print("\nЗнайдена адреса:", saved_street, saved_house)
        print("Групи:", ", ".join(groups))

        print("\nЗавантажуємо актуальний графік ДТЕК...")

        data = get_schedules()
        today_schedule = get_today_schedule(data)

        if not today_schedule:
            print("Немає актуального графіка на сьогодні.")
            return

        today = datetime.now(KYIV_TZ).date()

        for group in groups:
            hours = today_schedule.get(group)

            if hours is None:
                print(f"\nГрафік для групи {group} не знайдено.")
                continue

            outages = calculate_outages(hours, today)

            show_schedule(
                saved_street,
                saved_house,
                group,
                outages
            )

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