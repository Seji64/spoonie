#!/bin/bash
printenv > /etc/environment
echo "############### Starting initial run... ###############"
/usr/local/bin/python3 /app/spoonie.py --oauth-port "$SPOTIFY_OAUTH_PORT" \
        --tonie-username "$TONIE_USERNAME" --tonie-password "$TONIE_PASSWORD" --tonie-household "$TONIE_HOUSEHOLD" \
        --creative-tonie "$CREATIVE_TONIE" --tonie-timeout $TONIE_TIMEOUT --playlist "$PLAYLIST" --data-path "$DATA_PATH"
echo "############### Initial run completed! ###############"
echo "############### Starting CRON ###############"
/usr/bin/supercronic -passthrough-logs /app/crontab
