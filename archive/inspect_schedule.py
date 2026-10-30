
import json
import re
import requests

URL = "https://www.dtek-kem.com.ua/ua/shutdowns"

try:
    response = requests.get(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=20
    )
    response.raise_for_status()

    html = response.text

    print("Сторінка отримана:", response.status_code)

    patterns = [
        r"DisconSchedule\.fact\s*=",
        r"getHomeNum",
        r"getStreet",
        r"street"
    ]

    for pattern in patterns:
        print(
            f"\n{pattern}:",
            "знайдено" if re.search(pattern, html, re.I)
            else "не знайдено"
        )

    match = re.search(
        r"DisconSchedule\.fact\s*=\s*",
        html
    )

    if match:
        start = html.find("{", match.end())

        if start >= 0:
            data, _ = json.JSONDecoder().raw_decode(
                html[start:]
            )

            print("\nКлючі графіків:", list(data.keys()))

            groups = data.get("data", {})
            print("Кількість дат:", len(groups))

            for date, items in list(groups.items())[:2]:
                print("Дата:", date)
                print("Приклади груп:", list(items.keys())[:5])
    else:
        print("\nГрафік у початковому HTML не знайдено.")

except Exception as error:
    print("Помилка:", error)
