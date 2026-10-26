from datetime import datetime

print("=== Перевірка відключень світла ===")

print("1. Київ")
print("2. Київська область")

location = input("Оберіть розташування (1 або 2): ")

queue = input("Введіть свою чергу відключення (наприклад, 1.1): ")

print("\nВаші дані:")
    
if location == "1":
    print("Розташування: Київ")
elif location == "2":
    print("Розташування: Київська область")
else:
    print("Невідоме розташування!")

print("Черга відключення:", queue)

print("\nПрограму запущено успішно!")
print("Поточний час:", datetime.now().strftime("%H:%M:%S"))
