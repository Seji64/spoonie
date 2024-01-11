#!/bin/bash
printenv > /etc/environment
echo "############### Installing Cron Job ###############"
echo "${CRON} python3 /app/spoonie.py --spotify-user "$SPOTIFY_USERNAME" --spotify-password '${SPOTIFY_PASSWORD}' --tonie-username "$TONIE_USERNAME" --tonie-password '${TONIE_PASSWORD}' --tonie-household \"${TONIE_HOUSEHOLD}\" --creative-tonie \"${CREATIVE_TONIE}\" --playlist "$PLAYLIST" --data-path \"${DATA_PATH}\" > /proc/1/fd/1 2>/proc/1/fd/2" > /tmp/crontab.file
crontab -i /tmp/crontab.file
rm -f /tmp/crontab
crontab -l
echo "############### Cron Job installed ! ###############"
echo "############### Starting initial run... ###############"
python3 /app/spoonie.py --spotify-user "$SPOTIFY_USERNAME" --spotify-password "$SPOTIFY_PASSWORD" \
        --tonie-username "$TONIE_USERNAME" --tonie-password "$TONIE_PASSWORD" --tonie-household "$TONIE_HOUSEHOLD" \
        --creative-tonie "$CREATIVE_TONIE" --playlist "$PLAYLIST" --data-path "$DATA_PATH"
echo "############### Initial run completed! ###############"
echo "############### Starting CRON ###############"
cron -l 2 -f