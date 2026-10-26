import json
import re
import requests

from datetime import datetime
from zoneinfo import ZoneInfo

URL = "https://www.dtek-kem.com.ua/ua/shutdowns"
KYIV_TZ = ZoneInfo("Europe/Kyiv")


def get_schedules():
    response = requests.get(URL, timeout=20)
    response.raise_for_status()

    html = response.text

    match = re.search(
        r"DisconSchedule\.fact\s*=\s*",
        html
    )

    if not match:
        raise ValueError("Графіки ДТЕК не знайдено.")

    start = html.find("{", match.end())

    if start == -1:
        raise ValueError("Дані графіків пошкоджені.")

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


def show_schedule(group, hours):
    print(f"\nГрупа відключень: {group}")
    print(f"Дата: {datetime.now(KYIV_TZ):%d.%m.%Y}")
    print("-" * 40)

    print("Погодинні дані ДТЕК:\n")

    for hour in range(1, 25):
        status = hours.get(str(hour), "unknown")

        start_hour = hour - 1
        end_hour = hour

        start_time = f"{start_hour:02d}:00"
        end_time = f"{end_hour:02d}:00"

        if end_hour == 24:
            end_time = "24:00"

        print(
            f"{start_time} - {end_time}: {status}"
        )

    print("\nПозначення:")
    print("yes, no, first, second — значення ДТЕК.")
    print(
        "Їхнє точне значення ще перевіряється, "
        "тому програма поки не визначає "
        "час відключення автоматично."
    )


def main():
    print("=" * 45)
    print("     ГРАФІКИ ВІДКЛЮЧЕНЬ СВІТЛА")
    print("               КИЇВ")
    print("=" * 45)

    try:
        data = get_schedules()
        today_schedule = get_today_schedule(data)

        if not today_schedule:
            print("\nНемає графіків ДТЕК на сьогодні.")
            return

        groups = sorted(today_schedule.keys())

        print("\nДоступні групи:\n")

        for index, group in enumerate(groups, 1):
            print(f"{index}. {group}")

        choice = input(
            "\nВведіть номер своєї групи: "
        ).strip()

        if not choice.isdigit():
            print("Помилка: введіть число.")
            return

        index = int(choice) - 1

        if index < 0 or index >= len(groups):
            print("Такої групи немає.")
            return

        group = groups[index]
        hours = today_schedule[group]

        show_schedule(group, hours)

    except requests.RequestException as error:
        print("\nПомилка підключення:", error)

    except (ValueError, KeyError, TypeError) as error:
        print("\nПомилка обробки графіків:", error)


if __name__ == "__main__":
    main()