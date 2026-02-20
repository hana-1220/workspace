FROM python:3.12-slim

WORKDIR /app

# poppler for pdf2image
RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["gunicorn", "src.server:app", "--bind", "0.0.0.0:8080"]
