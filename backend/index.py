import secrets

# Генерируем случайный ключ длиной 32 байта (256 бит) и преобразуем в строку
secret_key = secrets.token_urlsafe(32)
print(secret_key)