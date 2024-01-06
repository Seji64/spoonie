FROM python:3.12-slim
LABEL org.opencontainers.image.authors="seji@tihoda.de"

ENV SPOTIFY_USERNAME=
ENV SPOTIFY_PASSWORD=
ENV TONIE_USERNAME=
ENV TONIE_PASSWORD=
ENV TONIE_HOUSEHOLD=
ENV DATA_PATH=/app/data
ENV CREATIVE_TONIE=
ENV PLAYLIST=

WORKDIR /app
COPY spoonie.py .
COPY requirements.txt .
COPY crontab /etc/cron.d/crontab
COPY entrypoint.sh .

RUN apt-get update && apt-get -y upgrade && \
    apt-get --no-install-suggests --no-install-recommends -y install git cron tini ffmpeg && \
    pip3 install --upgrade pip && \
    pip3 install -r requirements.txt && \
    chmod 0644 /etc/cron.d/crontab && \
    chmod +x /app/entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash", "/app/entrypoint.sh"]