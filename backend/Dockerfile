FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_MODE=server \
    HOST=0.0.0.0 \
    PORT=8710

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY backend /app/backend

RUN mkdir -p /app/data /app/media /app/catalog /app/logs \
    && useradd --uid 1000 --create-home --shell /usr/sbin/nologin cardgrader \
    && chown -R cardgrader:cardgrader /app/data /app/media /app/catalog /app/logs /app/backend

USER cardgrader

EXPOSE 8710

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8710"]
