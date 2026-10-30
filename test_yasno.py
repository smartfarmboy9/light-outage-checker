import requests

url = "https://app.yasno.ua/api/blackout-service/public/shutdowns/addresses/v2/group"

response = requests.get(
    url,
    params={
        "regionId": 25,
        "dsoId": 902,
        "streetId": 1512,
        "houseId": 15579
    },
    timeout=30
)

print("Статус:", response.status_code)
print("Відповідь:", response.text[:5000])