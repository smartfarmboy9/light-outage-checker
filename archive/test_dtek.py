import requests

url = "https://www.dtek-kem.com.ua/ua/ajax"

data = {
    "method": "getHomeNum",
    "data[0][name]": "street",
    "data[0][value]": "вул. Іленка Юрія",
    "data[1][name]": "updateFact",
    "data[1][value]": "26.10.2026 08:21"
}

try:
    response = requests.post(
        url,
        data=data,
        timeout=15
    )

    print("Статус:", response.status_code)
    print("Відповідь сервера:")
    print(response.text[:1000])

except requests.RequestException as error:
    print("Помилка:", error)