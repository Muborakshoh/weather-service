# Используем официальный образ Python
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 
RUN pip install emoji

COPY bot.py .

CMD ["python", "bot.py"]