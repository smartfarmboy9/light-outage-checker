import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.dtek-kem.com.ua"
PAGE_URL = BASE_URL + "/ua/shutdowns"
AJAX_URL = BASE_URL + "/ua/ajax"

session = requests.Session()

try:
    response = session.get(PAGE_URL, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    csrf_tag = soup.find("meta", attrs={"name": "csrf-token"})

    if csrf_tag is None:
        print("CSRF-токен не знайдено")
        exit()

    csrf_token = csrf_tag.get("content")

    headers = {
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL,
        "Referer": PAGE_URL,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    data = {
        "method": "getHomeNum",
        "data[0][name]": "street",
        "data[0][value]": "вул. Іленка Юрія",
        "data[1][name]": "updateFact",
        "data[1][value]": "26.10.2026 08:21",
    }

    response = session.post(
        AJAX_URL,
        data=data,
        headers=headers,
        timeout=20
    )

    print("HTTP:", response.status_code)

    result = response.json()

    print("Відповідь:", str(result)[:500])

    if result.get("result") is True:
        houses = result.get("data", {})

        print("\nЗнайдено будинків:", len(houses))

        for house, info in list(houses.items())[:20]:
            print(
                f"Будинок: {house} | "
                f"Група: {info.get('sub_type_reason')}"
            )
    else:
        print("\nДТЕК не повернув список будинків.")

except requests.RequestException as error:
    print("Помилка підключення:", error)

except ValueError:
    print("Сервер повернув некоректний JSON.")