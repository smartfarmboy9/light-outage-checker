
import json
import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

PAGE_URL = "https://www.dtek-kem.com.ua/ua/shutdowns"
OUTPUT_FILE = "addresses.json"
PROGRESS_FILE = "addresses_progress.json"

DELAY = 1.0
MAX_RETRIES = 3


def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    })

    page = session.get(PAGE_URL, timeout=30)
    page.raise_for_status()

    soup = BeautifulSoup(page.text, "html.parser")
    meta = soup.find("meta", attrs={"name": "ajaxUrl"})
    csrf_param = soup.find("meta", attrs={"name": "csrf-param"})
    csrf_token = soup.find("meta", attrs={"name": "csrf-token"})

    if not meta:
        raise RuntimeError("Не знайдено AJAX URL")

    ajax_url = urljoin(PAGE_URL, meta["content"])

    if csrf_param and csrf_token:
        session.headers["X-CSRF-Token"] = csrf_token["content"]
        session.csrf_param = csrf_param["content"]
        session.csrf_token = csrf_token["content"]
    else:
        session.csrf_param = None
        session.csrf_token = None

    session.headers["Referer"] = PAGE_URL
    return session, ajax_url


def api_request(session, ajax_url, payload):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = dict(payload)

            if session.csrf_param and session.csrf_token:
                data[session.csrf_param] = session.csrf_token

            response = session.post(
                ajax_url,
                data=data,
                timeout=30,
            )

            # Оновлюємо токен, якщо сайт повернув новий HTML
            if response.status_code in (400, 403):
                raise RuntimeError(
                    f"Сервер відхилив запит: HTTP {response.status_code}"
                )

            response.raise_for_status()
            result = response.json()

            if result.get("result"):
                return result

            raise RuntimeError(
                f"API повернув помилку: {result.get('text', result)}"
            )

        except Exception as error:
            print(f"  Спроба {attempt}/{MAX_RETRIES}: {error}")

            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)

    return None


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            print(f"Не вдалося прочитати {path}; використовую порожні дані.")
    return default


def save_json(path, data):
    temporary = path + ".tmp"

    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    os.replace(temporary, path)


def main():
    print("Підключаємося до ДТЕК...")

    try:
        session, ajax_url = create_session()
    except Exception as error:
        print("Не вдалося відкрити сайт:", error)
        return

    print("Отримуємо список вулиць...")

    result = api_request(
        session,
        ajax_url,
        {"method": "getStreets"},
    )

    if not result:
        print("Не вдалося отримати список вулиць.")
        return

    streets = result.get("streets", [])
    print("Усього вулиць:", len(streets))

    progress = load_json(PROGRESS_FILE, {
        "completed": [],
        "addresses": {},
    })

    completed = set(progress.get("completed", []))
    addresses = progress.get("addresses", {})

    for index, street in enumerate(streets, start=1):
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

        result = api_request(session, ajax_url, payload)

        if result is None:
            print("  Не вдалося отримати дані. Зупиняємося.")
            break

        houses = result.get("data", {})

        if not isinstance(houses, dict):
            print("  Невідомий формат відповіді. Зупиняємося.")
            break

        addresses[street] = houses
        completed.add(street)

        progress = {
            "completed": sorted(completed),
            "addresses": addresses,
        }

        save_json(PROGRESS_FILE, progress)

        # Періодично оновлюємо основний файл
        if index % 10 == 0:
            save_json(OUTPUT_FILE, addresses)
            print("  Проміжний результат збережено.")

        time.sleep(DELAY)

    save_json(OUTPUT_FILE, addresses)
    save_json(PROGRESS_FILE, {
        "completed": sorted(completed),
        "addresses": addresses,
    })

    print("\nГотово.")
    print("Оброблено вулиць:", len(completed), "із", len(streets))
    print("Адрес збережено у:", OUTPUT_FILE)
    print("Прогрес збережено у:", PROGRESS_FILE)

    if len(completed) < len(streets):
        print("Запусти файл ще раз, щоб продовжити збір.")


if __name__ == "__main__":
    main()
