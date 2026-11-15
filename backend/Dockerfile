# Ubuntu 24.04: Python 3.12 nativo, mesmo SO recomendado para o servidor.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
# ffmpeg (render), espeak-ng (TTS local), libegl1 (Skia), fontes para legendas/títulos, postgresql-client (espera/backup)
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv ca-certificates ffmpeg espeak-ng libegl1 libgl1 fontconfig fonts-inter fonts-dejavu-core \
      postgresql-client curl tini \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv && pip install --upgrade pip

WORKDIR /app
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install -e . && rm -rf app
COPY . .
RUN useradd -r -u 1001 -m factory && mkdir -p /data/storage /data/work && chown -R factory /data /app
USER factory
ENV STORAGE_LOCAL_PATH=/data/storage WORK_DIR=/data/work
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--", "./docker-entrypoint.sh"]
CMD ["api"]
