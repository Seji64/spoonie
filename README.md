# Spoonie - Sync a spotify playlist with a Creative Tonie

This (ugly) script can be used to sync a spotify playlist with a creative tonie of your choice. A free (burner) spotify account is enough - no premium is required(thanks to https://github.com/kokarare1212/librespot-python).

## Installation
```
git clone https://github.com/Seji64/spoonie
cd spoonie
pip3 install virtualenv
virtualenv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

## Usage

### Spotify Login

Spotify no longer supports the login with username / password. Instead spoonie uses the OAuth login (like [Zotify](https://github.com/Googolplexed0/zotify)):

1. If there is no `credentials.json` in the data path, spoonie logs a link and waits for the login.
2. Open the link in your browser and login to spotify.
3. Spotify redirects your browser to `http://127.0.0.1:4381/login?code=...`. Spoonie receives this request, completes the login and stores the credentials as `credentials.json` in the data path (Docker: `/app/data/credentials.json`). Further runs use the stored credentials.

If spoonie runs on another machine (e.g. a server), the redirect page can't be loaded in your browser. In this case copy the complete url from the address bar of your browser and open it on the machine spoonie runs on, e.g. `curl "http://127.0.0.1:4381/login?code=..."`.

If the stored credentials are no longer valid, delete `credentials.json` and restart spoonie to login again. An existing `credentials.json` (e.g. created via https://github.com/dspearson/librespot-auth) still works.

### Local
```
cd spoonie
source venv/bin/activate
python3 spoonie.py --tonie-username <tonies.com user> --tonie-password <password> --tonie-household <eg. Sejis Haushalt> --creative-tonie <creative tonie name> --playlist <spotify-playist-url>
```

### Docker
```
docker run -d --restart=unless-stopped \
  -v /folder/data:/app/data \
  -p 4381:4381 \
  -e TONIE_USERNAME=<tonies.com username> \
  -e TONIE_PASSWORD=<tonies.com password> \
  -e TONIE_HOUSEHOLD=<household name> \
  -e CREATIVE_TONIE=<tonie name> \
  -e PLAYLIST=<playlist_url> \
  --name spoonie ghcr.io/seji64/spoonie:latest
```

# Inspiration and used libs
- [Zotify](https://github.com/Googolplexed0/zotify)
- [librespot-python](https://github.com/Googolplexed0/librespot-python)
- [tonie_api](https://github.com/Wilhelmsson177/tonie-api)
- https://github.com/stefanbesler/tony
