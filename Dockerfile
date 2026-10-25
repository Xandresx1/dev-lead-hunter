FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    TZ=America/Lima

RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
VOLUME ["/data"]

HEALTHCHECK --interval=5m --timeout=10s --retries=3 \
  CMD python -c "import os,time,sys; p='/data/hunter.log'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 3600 else 1)"

CMD ["python", "main.py"]
