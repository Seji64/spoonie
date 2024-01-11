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
COPY entrypoint.sh .
COPY crontab.yaml .

RUN apt-get update && apt-get -y upgrade && \
    apt-get --no-install-suggests --no-install-recommends -y install git tini ffmpeg curl && \
    curl -L "https://github.com/gjcarneiro/yacron/releases/download/0.19.0/yacron-0.19.0-x86_64-unknown-linux-gnu" --output /usr/local/bin/yacron && \
    pip3 install --upgrade pip && \
    pip3 install -r requirements.txt && \
    chmod +x /app/entrypoint.sh && \
    chmod +x /usr/local/bin/yacron

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash", "/app/entrypoint.sh"]