import json
import re
import requests
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

API = "https://app.yasno.ua/api/blackout-service/public/shutdowns/regions/25/dsos/902/planned-outages"
ADDRESSES = Path(__file__).with_name("addresses.json")
TZ = ZoneInfo("Europe/Kyiv")


def normalize(text):
    text = text.casefold().replace("’", "'").replace("ʼ", "'")
    text = re.sub(r"\s+", " ", text).strip()
    prefixes = ("вул.", "вулиця", "просп.", "проспект",
                "пров.", "провулок", "бул.", "бульвар",
                "пл.", "площа", "шосе")
    for prefix in prefixes:
        if text.startswith(prefix + " "):
            return text[len(prefix):].strip()
    return text


def load_addresses():
    with open(ADDRESSES, encoding="utf-8") as file:
        data = json.load(file)
    return data.get("Київ", data)


def find_street(addresses):
    while True:
        query = normalize(input("\nВведіть вулицю: "))
        if not query:
            continue
        matches = [name for name in addresses if query in normalize(name)]
        if not matches:
            print("Вулицю не знайдено.")
            continue
        matches.sort(key=lambda name: (not normalize(name).startswith(query), name))
        for i, name in enumerate(matches, 1):
            print(f"{i}. {name}")
        if len(matches) == 1:
            if input("Це ваша вулиця? (так/ні): ").lower() in ("так", "т"):
                return matches[0]
            continue
        choice = input("Оберіть номер (0 - назад): ")
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            return matches[int(choice) - 1]


def find_house(houses):
    while True:
        query = input("\nВведіть номер будинку: ").strip().casefold()
        query = re.sub(r"[\s/-]", "", query)
        for house, info in houses.items():
            if re.sub(r"[\s/-]", "", house.casefold()) == query:
                return house, info
        print("Будинок не знайдено. Спробуйте ще раз.")


def get_group(info):
    if isinstance(info, dict):
        if info.get("yasno_group"):
            return str(info["yasno_group"])
        groups = info.get("sub_type_reason", [])
    else:
        groups = info
    if isinstance(groups, str):
        groups = [groups]
    if not isinstance(groups, list):
        groups = []
    found = []
    for group in groups:
        if isinstance(group, str):
            match = re.fullmatch(r"GPV(\d+\.\d+)", group, re.I)
            if match:
                found.append(match.group(1))
    found = list(dict.fromkeys(found))
    if len(found) != 1:
        raise ValueError("Не вдалося однозначно визначити групу.")
    return found[0]


def get_schedules():
    response = requests.get(API, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Неправильна відповідь YASNO.")
    return data


def parse_day(data):
    if not isinstance(data, dict) or not data.get("date"):
        return None
    date = datetime.fromisoformat(data["date"].replace("Z", "+00:00"))
    if date.tzinfo:
        date = date.astimezone(TZ)
    day = date.date()
    status = data.get("status")
    start_day = datetime(day.year, day.month, day.day, tzinfo=TZ)
    outages, possible = [], []
    for slot in data.get("slots", []):
        kind = slot.get("type")
        if kind not in ("Definite", "Possible"):
            continue
        start_min, end_min = int(slot["start"]), int(slot["end"])
        if not 0 <= start_min < end_min <= 1440:
            continue
        interval = (start_day + timedelta(minutes=start_min),
                    start_day + timedelta(minutes=end_min))
        (outages if kind == "Definite" else possible).append(interval)
    return {"date": day, "status": status,
            "outages": sorted(outages), "possible": sorted(possible)}


def duration(delta):
    minutes = max(0, int(delta.total_seconds() // 60))
    return f"{minutes // 60} год {minutes % 60} хв"


def show_day(title, data):
    print(f"\n{title}")
    if not data:
        print("Графік недоступний.")
        return
    print("Дата:", data["date"].strftime("%d.%m.%Y"))
    if data["status"] == "EmergencyShutdowns":
        print("Екстрені відключення. Плановий графік не діє.")
        return
    if data["status"] == "NoShutdowns":
        print("Планових відключень немає.")
        return
    if not data["outages"]:
        print("Підтверджених відключень немає.")
    for start, end in data["outages"]:
        print(f"{start:%H:%M} - {end:%H:%M}")
    if data["possible"]:
        print("Можливі відключення:")
        for start, end in data["possible"]:
            print(f"{start:%H:%M} - {end:%H:%M}")


def show_status(today, tomorrow):
    now = datetime.now(TZ)
    print(f"\nПоточний час: {now:%H:%M}")
    if not today or today["date"] != now.date():
        print("Актуального графіка на сьогодні немає.")
        return
    if today["status"] == "EmergencyShutdowns":
        print("Екстрені відключення. Час невідомий.")
        return
    outages = list(today["outages"])
    if tomorrow and tomorrow["date"] == now.date() + timedelta(days=1):
        if tomorrow["status"] not in ("EmergencyShutdowns", "NoShutdowns"):
            outages += tomorrow["outages"]
    for start, end in sorted(outages):
        if start <= now < end:
            print("За графіком світла немає.")
            print("Відновлення:", end.strftime("%H:%M"))
            print("До відновлення:", duration(end - now))
            return
        if now < start:
            print("За графіком світло є.")
            print("Наступне відключення:", start.strftime("%d.%m %H:%M"))
            print("Відновлення:", end.strftime("%d.%m %H:%M"))
            print("До відключення:", duration(start - now))
            return
    print("Майбутніх підтверджених відключень не знайдено.")
    if today["possible"]:
        print("Увага: можливі відключення також є у графіку.")


def main():
    print("=" * 45)
    print("ПЕРЕВІРКА ВІДКЛЮЧЕНЬ СВІТЛА - КИЇВ")
    print("=" * 45)
    try:
        addresses = load_addresses()
        street = find_street(addresses)
        house, info = find_house(addresses[street])
        group = get_group(info)
        print(f"\nАдреса: {street}, {house}")
        print(f"Група YASNO за номером GPV: {group}")
        print("Увага: відповідність групи не гарантована.")
        print("\nЗавантаження графіка YASNO...")
        schedules = get_schedules()
        if group not in schedules:
            print("Групу не знайдено в API YASNO.")
            return
        data = schedules[group]
        today = parse_day(data.get("today"))
        tomorrow = parse_day(data.get("tomorrow"))
        print("\n" + "=" * 45)
        print("ГРАФІК ВІДКЛЮЧЕНЬ")
        print("=" * 45)
        show_day("СЬОГОДНІ", today)
        show_day("ЗАВТРА", tomorrow)
        print("\n" + "-" * 45)
        show_status(today, tomorrow)
        print("\nДжерело: YASNO")
        print("Фактичні відключення можуть відрізнятися.")
    except FileNotFoundError:
        print("Помилка: addresses.json не знайдено.")
    except requests.RequestException as error:
        print("Помилка API YASNO:", error)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print("Помилка:", error)
    except KeyboardInterrupt:
        print("\nПрограму зупинено.")


if __name__ == "__main__":
    main()