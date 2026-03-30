FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import os, sys, urllib.request; port=os.getenv('HEALTHCHECK_PORT', '8080'); url=f'http://127.0.0.1:{port}/healthz'; sys.exit(0 if urllib.request.urlopen(url, timeout=3).getcode() == 200 else 1)"

CMD ["python", "app.py"]
