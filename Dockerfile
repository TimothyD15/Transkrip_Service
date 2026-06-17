FROM python:3.10

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

ENV NAMEKO_CONFIG=config.yml
ENV PYTHONUNBUFFERED=1

# Jalankan kedua service (Transkrip RPC service & Gateway HTTP service)
# dalam satu proses Nameko, menggunakan config.yml yang sama.
CMD ["nameko", "run", "--config", "config.yml", "Transkrip.service:TranskripService", "gateway.service:GatewayService"]
