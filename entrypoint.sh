#!/bin/bash
printenv > /etc/environment
echo "############### Starting initial run... ###############"
/usr/local/bin/python3 /app/spoonie.py --spotify-user "$SPOTIFY_USERNAME" --spotify-password "$SPOTIFY_PASSWORD" \
        --tonie-username "$TONIE_USERNAME" --tonie-password "$TONIE_PASSWORD" --tonie-household "$TONIE_HOUSEHOLD" \
        --creative-tonie "$CREATIVE_TONIE" --tonie-timeout $TONIE_TIMEOUT --playlist "$PLAYLIST" --data-path "$DATA_PATH"
echo "############### Initial run completed! ###############"
echo "############### Starting CRON ###############"
/usr/local/bin/yacron -c /app/crontab.yaml