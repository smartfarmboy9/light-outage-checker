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

MAX_RUNTIME = 15 * 60
MAX_STREETS_PER_RUN = 300
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

        except (requests.RequestException, ValueError, RuntimeError) as error:
            print(
                f"Помилка запиту ({attempt}/{MAX_RETRIES}): {error}",
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

    print("=" * 50)
    print("ОНОВЛЕННЯ БАЗИ АДРЕС ДТЕК")
    print("=" * 50)

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

        # Залишаємо лише актуальні вулиці
        current_streets = set(streets)
        completed &= current_streets
        addresses = {
            street: houses
            for street, houses in addresses.items()
            if street in current_streets
        }

        consecutive_errors = 0
        processed_this_run = 0

        for index, street in enumerate(streets, 1):
            if street in completed:
                continue

            elapsed = time.monotonic() - start_time

            if (
                elapsed >= MAX_RUNTIME
                or processed_this_run >= MAX_STREETS_PER_RUN
            ):
                save_progress(completed, addresses)

                print(
                    f"\nПроміжний результат: "
                    f"{len(completed)}/{len(streets)} вулиць.",
                    flush=True,
                )
                print("Прогрес збережено. Продовжимо наступного запуску.")
                return

            print(f"[{index}/{len(streets)}] {street}", flush=True)

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

            if result is None or not isinstance(result.get("data"), dict):
                consecutive_errors += 1

                print(f"Не вдалося обробити: {street}", flush=True)

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    save_progress(completed, addresses)
                    raise RuntimeError(
                        "Забагато помилок поспіль. Прогрес збережено."
                    )

                time.sleep(DELAY)
                continue

            consecutive_errors = 0

            addresses[street] = result["data"]
            completed.add(street)
            processed_this_run += 1

            # Зберігаємо після кожної успішної вулиці
            save_progress(completed, addresses)

            time.sleep(DELAY)

        missing = current_streets - completed

        if missing:
            save_progress(completed, addresses)

            print(
                f"\nЗалишилося обробити вулиць: {len(missing)}",
                flush=True,
            )
            print("Прогрес збережено. Продовжимо наступного запуску.")
            return

        total_houses = sum(
            len(houses)
            for houses in addresses.values()
            if isinstance(houses, dict)
        )

        if len(addresses) < 2000 or total_houses < 10000:
            raise RuntimeError(
                "Перевірка бази не пройдена. Основну базу не змінено."
            )

        # Оновлюємо основну базу тільки після повного збору
        save_json(ADDRESSES_FILE, addresses)

        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()

        print("\n" + "=" * 50)
        print("БАЗУ УСПІШНО ОНОВЛЕНО")
        print("=" * 50)

        print("Вулиць:", len(addresses))
        print("Адрес:", total_houses)
        print(
            "Дата оновлення:",
            datetime.now(KYIV_TZ).strftime("%d.%m.%Y %H:%M"),
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