FROM python:3.12-slim

# System deps: ExifTool (metadata), Tesseract (OCR), OpenCV runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    exiftool \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm

COPY . .

ENV PYTHONPATH=/app
ENV CLAIM_AI_ENCRYPTION_KEY=""
# Generate key at runtime if unset — set CLAIM_AI_ENCRYPTION_KEY in production.

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
