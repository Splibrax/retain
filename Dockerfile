FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/
COPY data/ ./data/
COPY ui/ ./ui/
COPY main.py .

EXPOSE 8080
# Runtime yêu cầu bind 0.0.0.0 chứ không phải 127.0.0.1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
