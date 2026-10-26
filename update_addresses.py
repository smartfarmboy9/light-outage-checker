import json
import os
import time
import requests

from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent

PAGE_URL = "https://www.dtek-kem.com.ua/ua/shutdowns"
ADDRESSES_FILE = BASE_DIR / "addresses.json"
PROGRESS_FILE = BASE_DIR / "addresses_update_progress.json"

DELAY = 1.5
MAX_RETRIES = 3

KYIV_TZ = ZoneInfo("Europe/Kyiv")


def save_json(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")

    with open(temp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    os.replace(temp, path)


def load_json(path, default):
    if not path.exists():
        return default

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def connect():
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": PAGE_URL,
    })

    response = session.get(PAGE_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    ajax_meta = soup.find("meta", attrs={"name": "ajaxUrl"})
    csrf_meta = soup.find("meta", attrs={"name": "csrf-token"})
    csrf_param = soup.find("meta", attrs={"name": "csrf-param"})

    if not ajax_meta or not csrf_meta or not csrf_param:
        raise RuntimeError("Не вдалося отримати параметри API ДТЕК.")

    session.headers["X-CSRF-Token"] = csrf_meta["content"]

    return (
        session,
        urljoin(PAGE_URL, ajax_meta["content"]),
        csrf_param["content"],
        csrf_meta["content"],
    )


def api_request(session, ajax_url, csrf_name, csrf_token, payload):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = list(payload)
            data.append((csrf_name, csrf_token))

            response = session.post(
                ajax_url,
                data=data,
                timeout=30,
            )

            response.raise_for_status()
            result = response.json()

            if result.get("result") is not True:
                raise RuntimeError(
                    f"Помилка API: {result.get('text', 'невідома')}"
                )

            return result

        except (requests.RequestException, ValueError, RuntimeError) as error:
            print(f"Спроба {attempt}/{MAX_RETRIES}: {error}")

            if attempt < MAX_RETRIES:
                time.sleep(attempt * 3)

    return None


def main():
    print("=" * 50)
    print("ОНОВЛЕННЯ БАЗИ АДРЕС ДТЕК")
    print("=" * 50)

    try:
        session, ajax_url, csrf_name, csrf_token = connect()

        result = api_request(
            session,
            ajax_url,
            csrf_name,
            csrf_token,
            [("method", "getStreets")],
        )

        if not result:
            print("Не вдалося отримати список вулиць.")
            return

        streets = result.get("streets", [])

        if not isinstance(streets, list) or not streets:
            print("Список вулиць порожній або некоректний.")
            return

        print("Знайдено вулиць:", len(streets))

        progress = load_json(PROGRESS_FILE, {
            "completed": [],
            "addresses": {},
        })

        completed = set(progress.get("completed", []))
        addresses = progress.get("addresses", {})

        for index, street in enumerate(streets, 1):
            if street in completed:
                continue

            print(f"[{index}/{len(streets)}] {street}")

            payload = [
                ("method", "getHomeNum"),
                ("data[0][name]", "street"),
                ("data[0][value]", street),
                ("data[1][name]", "house_num"),
                ("data[1][value]", ""),
            ]

            result = api_request(
                session,
                ajax_url,
                csrf_name,
                csrf_token,
                payload,
            )

            if result is None:
                print("Оновлення перервано. Прогрес збережено.")
                return

            houses = result.get("data", {})

            if not isinstance(houses, dict):
                print("Некоректні дані будинків. Оновлення зупинено.")
                return

            addresses[street] = houses
            completed.add(street)

            save_json(PROGRESS_FILE, {
                "completed": sorted(completed),
                "addresses": addresses,
            })

            time.sleep(DELAY)

        # Основну базу замінюємо тільки після повного збору
        save_json(ADDRESSES_FILE, addresses)

        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()

        total_houses = sum(
            len(houses)
            for houses in addresses.values()
            if isinstance(houses, dict)
        )

        print("\n" + "=" * 50)
        print("БАЗУ УСПІШНО ОНОВЛЕНО")
        print("=" * 50)

        print("Вулиць:", len(addresses))
        print("Адрес:", total_houses)
        print(
            "Дата оновлення:",
            datetime.now(KYIV_TZ).strftime("%d.%m.%Y %H:%M"),
        )

    except (requests.RequestException, RuntimeError, OSError, ValueError) as error:
        print("Помилка оновлення:", error)


if __name__ == "__main__":
    main()