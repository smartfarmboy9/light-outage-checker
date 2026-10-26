import json
import os
import sys
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

KYIV_TZ = ZoneInfo("Europe/Kyiv")

DELAY = 1.5
MAX_RETRIES = 2
REQUEST_TIMEOUT = (10, 15)

# Максимальний час одного запуску — 45 хвилин
MAX_RUNTIME = 45 * 60

# Після 10 невдалих вулиць поспіль зупиняємося
MAX_CONSECUTIVE_ERRORS = 10


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

    response = session.get(PAGE_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    ajax_meta = soup.find("meta", attrs={"name": "ajaxUrl"})
    csrf_meta = soup.find("meta", attrs={"name": "csrf-token"})
    csrf_param = soup.find("meta", attrs={"name": "csrf-param"})

    if not ajax_meta or not csrf_meta or not csrf_param:
        raise RuntimeError("Не знайдено параметри API ДТЕК.")

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
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            result = response.json()

            if result.get("result") is not True:
                raise RuntimeError(
                    f"API: {result.get('text', 'невідома помилка')}"
                )

            return result

        except (
            requests.RequestException,
            ValueError,
            RuntimeError,
        ) as error:

            print(
                f"Помилка запиту "
                f"({attempt}/{MAX_RETRIES}): {error}",
                flush=True,
            )

            if attempt < MAX_RETRIES:
                time.sleep(3)

    return None


def save_progress(completed, addresses):
    save_json(PROGRESS_FILE, {
        "completed": sorted(completed),
        "addresses": addresses,
    })


def main():
    start_time = time.monotonic()

    print("=" * 50, flush=True)
    print("ОНОВЛЕННЯ БАЗИ АДРЕС ДТЕК", flush=True)
    print("=" * 50, flush=True)

    session, ajax_url, csrf_name, csrf_token = connect()

    try:
        result = api_request(
            session,
            ajax_url,
            csrf_name,
            csrf_token,
            [("method", "getStreets")],
        )

        if result is None:
            raise RuntimeError("Не вдалося отримати список вулиць.")

        streets = result.get("streets", [])

        if not isinstance(streets, list) or not streets:
            raise RuntimeError("Список вулиць порожній.")

        print(f"Знайдено вулиць: {len(streets)}", flush=True)

        progress = load_json(PROGRESS_FILE, {
            "completed": [],
            "addresses": {},
        })

        completed = set(progress.get("completed", []))
        addresses = progress.get("addresses", {})

        consecutive_errors = 0
        failed_streets = []

        for index, street in enumerate(streets, 1):

            if street in completed:
                continue

            elapsed = time.monotonic() - start_time

            if elapsed >= MAX_RUNTIME:
                save_progress(completed, addresses)

                print(
                    "\nДосягнуто обмеження часу.",
                    flush=True,
                )

                raise RuntimeError(
                    "Оновлення не завершено. "
                    "Прогрес збережено локально."
                )

            print(
                f"[{index}/{len(streets)}] {street}",
                flush=True,
            )

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
                failed_streets.append(street)
                consecutive_errors += 1

                print(
                    f"Пропущено: {street}",
                    flush=True,
                )

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    save_progress(completed, addresses)

                    raise RuntimeError(
                        "Забагато помилок поспіль. "
                        "Перевір доступність API ДТЕК."
                    )

                time.sleep(DELAY)
                continue

            houses = result.get("data")

            if not isinstance(houses, dict):
                failed_streets.append(street)
                consecutive_errors += 1
                continue

            consecutive_errors = 0

            addresses[street] = houses
            completed.add(street)

            save_progress(completed, addresses)

            time.sleep(DELAY)

        if failed_streets:
            save_progress(completed, addresses)

            print("\nНе вдалося обробити вулиці:", flush=True)

            for street in failed_streets:
                print("-", street, flush=True)

            raise RuntimeError(
                f"Оновлення неповне: "
                f"{len(failed_streets)} вулиць не оброблено."
            )

        missing = set(streets) - completed

        if missing:
            save_progress(completed, addresses)

            raise RuntimeError(
                f"Не оброблено {len(missing)} вулиць."
            )

        # Перевіряємо результат перед заміною бази
        if len(addresses) < 2000:
            raise RuntimeError(
                "Підозріло мала кількість вулиць."
            )

        total_houses = sum(
            len(houses)
            for houses in addresses.values()
            if isinstance(houses, dict)
        )

        if total_houses < 10000:
            raise RuntimeError(
                "Підозріло мала кількість адрес."
            )

        # Замінюємо основну базу лише після успішної перевірки
        save_json(ADDRESSES_FILE, addresses)

        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()

        print("\n" + "=" * 50, flush=True)
        print("БАЗУ УСПІШНО ОНОВЛЕНО", flush=True)
        print("=" * 50, flush=True)

        print("Вулиць:", len(addresses), flush=True)
        print("Адрес:", total_houses, flush=True)

        print(
            "Дата оновлення:",
            datetime.now(KYIV_TZ).strftime("%d.%m.%Y %H:%M"),
            flush=True,
        )

    finally:
        session.close()


if __name__ == "__main__":
    try:
        main()

    except (
        requests.RequestException,
        RuntimeError,
        OSError,
        ValueError,
    ) as error:
        print(f"\nПомилка оновлення: {error}", flush=True)
        sys.exit(1)