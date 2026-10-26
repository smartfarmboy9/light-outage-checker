import urllib.request

url = "https://www.dtek-kem.com.ua/ua/shutdowns"

try:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    response = urllib.request.urlopen(request, timeout=10)
    print("Підключення працює!")
    print("Код відповіді:", response.status)
    response.close()
except Exception as error:
    print("Не вдалося підключитися.")
    print("Помилка:", error)
