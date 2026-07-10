# syntax=docker/dockerfile:1

FROM node:22-alpine AS web-builder

WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci

COPY web/ ./
RUN npm run build


FROM python:3.13-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app.py config.py database.py logger.py main.py ./
COPY core ./core
COPY handler ./handler
COPY middleware ./middleware
COPY model ./model
COPY router ./router
COPY schema ./schema
COPY service ./service
COPY utils ./utils
COPY --from=web-builder /app/web/dist-app ./web/dist-app

EXPOSE 8000

CMD ["python", "main.py"]
