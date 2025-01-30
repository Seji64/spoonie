FROM python:3.13-alpine as base

RUN apk --update add ffmpeg

FROM base AS builder

WORKDIR /install
COPY requirements.txt /requirements.txt
RUN apk add python3 py3-pip gcc libc-dev zlib zlib-dev jpeg-dev git
RUN pip install --prefix="/install" -r /requirements.txt

FROM base
LABEL org.opencontainers.image.authors="seji@tihoda.de"

ENV SPOTIFY_USERNAME=
ENV SPOTIFY_PASSWORD=
ENV TONIE_USERNAME=
ENV TONIE_PASSWORD=
ENV TONIE_HOUSEHOLD=
ENV TONIE_TIMEOUT=30
ENV DATA_PATH=/app/data
ENV CREATIVE_TONIE=
ENV PLAYLIST=

COPY --from=builder /install /usr/local/lib/python3.13/site-packages
RUN mv /usr/local/lib/python3.13/site-packages/lib/python3.13/site-packages/* /usr/local/lib/python3.13/site-packages/
RUN apk --no-cache add tini bash supercronic

WORKDIR /app
COPY spoonie.py .
COPY entrypoint.sh .
COPY crontab .

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/bin/bash", "/app/entrypoint.sh"]