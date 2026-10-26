FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKBENCH_DATA_DIR=/data \
    WORKBENCH_HOST=0.0.0.0 \
    WORKBENCH_PORT=8765

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY index.html app.js styles.css ui-apple-hig.css ./
COPY APPLE-HIG-DESIGN-SPEC.md README.md ./

RUN mkdir -p /data

EXPOSE 8765

CMD ["sh", "-c", "python -m uvicorn backend.main:app --host ${WORKBENCH_HOST} --port ${WORKBENCH_PORT}"]
