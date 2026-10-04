FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer libreoffice-core fonts-dejavu-core fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-portal.txt .
RUN pip install --no-cache-dir -r requirements-portal.txt
COPY . .
ENV PORT=10000
CMD ["sh","-c","gunicorn --bind 0.0.0.0:$PORT portal_app:app"]
