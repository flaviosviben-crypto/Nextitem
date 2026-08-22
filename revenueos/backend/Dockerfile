FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir -p /app/storage

EXPOSE 8000
# Shell form so an assigned $PORT wins; compose leaves it unset and gets 8000.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
