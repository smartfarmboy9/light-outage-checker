import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE = "https://app.yasno.ua/api/blackout-service/public/shutdowns"
REGION = 25
DSO = 902
TZ = ZoneInfo("Europe/Kyiv")


def api(path, params=None):
    response = requests.get(
        f"{BASE}/{path}",
        params=params,
        timeout=30
    )
    response.raise_for_status()
    return response.json()


def choose(items, title):
    if not items:
        raise ValueError("Нічого не знайдено.")

    print(f"\n{title}")

    for number, item in enumerate(items, 1):
        print(f"{number}. {item['value']}")

    while True:
        choice = input("\nОберіть номер: ").strip()

        if choice.isdigit() and 1 <= int(choice) <= len(items):
            return items[int(choice) - 1]

        print("Неправильний номер.")


def find_address():
    params = {"regionId": REGION, "dsoId": DSO}

    while True:
        query = input("\nВведіть назву вулиці: ").strip()

        if not query:
            continue

        streets = api(
            "addresses/v2/streets",
            {**params, "query": query}
        )

        if streets:
            break

        print("Вулицю не знайдено. Спробуйте ще раз.")

    street = choose(streets, "Знайдені вулиці:")

    houses = api(
        "addresses/v2/houses",
        {**params, "streetId": street["id"]}
    )

    while True:
        house_number = input("\nВведіть номер будинку: ").strip()

        matches = [
            house for house in houses
            if house["value"].casefold() == house_number.casefold()
        ]

        if matches:
            house = matches[0]
            break

        print("Будинок не знайдено. Спробуйте ще раз.")

    group_data = api(
        "addresses/v2/group",
        {
            **params,
            "streetId": street["id"],
            "houseId": house["id"]
        }
    )

    group = f"{group_data['group']}.{group_data['subgroup']}"

    return street["value"], house["value"], group


def parse_day(data):
    if not data or not data.get("date"):
        return None

    date = datetime.fromisoformat(
        data["date"].replace("Z", "+00:00")
    )

    if date.tzinfo:
        date = date.astimezone(TZ)

    day = date.date()
    start = datetime(day.year, day.month, day.day, tzinfo=TZ)

    outages = []
    possible = []

    for slot in data.get("slots", []):
        kind = slot.get("type")

        if kind not in ("Definite", "Possible"):
            continue

        first = start + timedelta(minutes=int(slot["start"]))
        last = start + timedelta(minutes=int(slot["end"]))

        if kind == "Definite":
            outages.append((first, last))
        else:
            possible.append((first, last))

    return {
        "date": day,
        "status": data.get("status"),
        "outages": sorted(outages),
        "possible": sorted(possible)
    }


def show_day(title, data):
    print(f"\n{title}")

    if not data:
        print("Графік недоступний.")
        return

    print("Дата:", data["date"].strftime("%d.%m.%Y"))

    if data["status"] == "EmergencyShutdowns":
        print("Екстрені відключення.")
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
        print("Екстрені відключення. Точний час невідомий.")
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


def duration(delta):
    minutes = max(0, int(delta.total_seconds() // 60))
    return f"{minutes // 60} год {minutes % 60} хв"


def main():
    print("=" * 45)
    print("ПЕРЕВІРКА ВІДКЛЮЧЕНЬ СВІТЛА - КИЇВ")
    print("=" * 45)

    try:
        street, house, group = find_address()

        print(f"\nАдреса: {street}, {house}")
        print(f"Група: {group}")
        print("\nЗавантаження графіка YASNO...")

        schedules = api(
            f"regions/{REGION}/dsos/{DSO}/planned-outages"
        )

        if group not in schedules:
            print("Графік для цієї групи не знайдено.")
            return

        data = schedules[group]
        today = parse_day(data.get("today"))
        tomorrow = parse_day(data.get("tomorrow"))

        print("\n" + "=" * 45)
        print("ГРАФІК ВІДКЛЮЧЕНЬ")
        print("=" * 45)

        show_day("СЬОГОДНІ", today)
        show_day("ЗАВТРА", tomorrow)
        show_status(today, tomorrow)

        print("\nДжерело: YASNO")
        print("Фактичні відключення можуть відрізнятися.")

    except requests.RequestException as error:
        print("Помилка підключення:", error)
    except (ValueError, KeyError, TypeError) as error:
        print("Помилка:", error)
    except KeyboardInterrupt:
        print("\nПрограму зупинено.")


if __name__ == "__main__":
    main()