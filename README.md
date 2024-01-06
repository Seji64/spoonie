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

### Local
```
cd spoonie
source venv/bin/activate
python3 spoonie.py --spotify-username <username> --spotify-password <password> --tonie-username <tonies.com user> --tonie-password <password> --tonie-household <eg. Sejis Haushalt> --creative-tonie <creative tonie name> --playlist <spotify-playist-url>
```

### Docker
```
docker run -d --restart=unless-stopped \
  -v /folder/data:/app/data \
  -e SPOTIFY_USERNAME=<spotify user> \
  -e SPOTIFY_PASSWORD=<password> \
  -e TONIE_USERNAME=<tonies.com username> \
  -e TONIE_PASSWORD=<tonies.com password> \
  -e TONIE_HOUSEHOLD=<household name> \
  -e CREATIVE_TONIE=<tonie name> \
  -e PLAYLIST=<playlist_url> \
  --name spoonie ghcr.io/seji64/spoonie:latest
```

# Inspiration and used libs
- [Zotify](https://zotify.xyz/)
- [librespot-python](https://github.com/kokarare1212/librespot-python)
- [tonie_api](https://github.com/Wilhelmsson177/tonie-api)
- https://github.com/stefanbesler/tony