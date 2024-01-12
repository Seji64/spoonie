# !/usr/bin/env python3

import logging
import requests
import re
import json
import os
import subprocess
import sys
import time
import glob
import math
import http.client
import urllib
import music_tag
import tempfile
import ffmpy
import shutil

from pathlib import Path
from librespot.audio.decoders import VorbisOnlyAudioQuality
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.core import Session
from tonie_api.api import TonieAPI
from tonie_api.models import Config, CreativeTonie, User

from argparse import ArgumentParser

PLAYLISTS_URL = 'https://api.spotify.com/v1/playlists'
TRACKS_URL = 'https://api.spotify.com/v1/tracks'

usage = """
""".format(sys.version, os.path.basename(__file__))

parser = ArgumentParser(usage=usage)
parser.add_argument("-su", "--spotify-username", dest="spotify_username", required=True, help="")
parser.add_argument("-sp", "--spotify-password", dest="spotify_password", required=True, help="")
parser.add_argument("-tu", "--tonie-username", dest="tonie_username", required=True, help="")
parser.add_argument("-tp", "--tonie-password", dest="tonie_password", required=True, help="")
parser.add_argument("-th", "--tonie-household", dest="tonie_household", required=True, help="Name of the 'meine Tonies' Haushalt")
parser.add_argument("-ctn", "--creative-tonie", dest="creative_tonie_name", required=True, help="Name of the creative tonie")
parser.add_argument("-P", "--playlist", dest="playlist", required=True, help="Link you get be clicking 'Invite  collaborators' in Spotify")
parser.add_argument("-d", "--data-path", dest="data_path", required=False, help="Defaults to ~/.local/share/spoonie")
parser.add_argument("-b", "--ban-protection", action="store_true", dest="ban_protection", required=False, help="Ban protection")

args = parser.parse_args()

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s | %(message)s' )

def fix_filename(name):
    """
    Replace invalid characters on Linux/Windows/MacOS with underscores.
    List from https://stackoverflow.com/a/31976060/819417
    Trailing spaces & periods are ignored on Windows.
    >>> fix_filename("  COM1  ")
    '_ COM1 _'
    >>> fix_filename("COM10")
    'COM10'
    >>> fix_filename("COM1,")
    'COM1,'
    >>> fix_filename("COM1.txt")
    '_.txt'
    >>> all('_' == fix_filename(chr(i)) for i in list(range(32)))
    True
    """
    return re.sub(r'[/\\:|<>"?*\0-\x1f]|^(AUX|COM[1-9]|CON|LPT[1-9]|NUL|PRN)(?![^.])|^\s|[\s.]$', "_", str(name), flags=re.IGNORECASE)

def regex_input_for_urls(search_input) -> tuple[str, str, str, str, str, str]:
    """ Since many kinds of search may be passed at the command line, process them all here. """
    track_uri_search = re.search(
        r'^spotify:track:(?P<TrackID>[0-9a-zA-Z]{22})$', search_input)
    track_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/track/(?P<TrackID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    album_uri_search = re.search(
        r'^spotify:album:(?P<AlbumID>[0-9a-zA-Z]{22})$', search_input)
    album_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/album/(?P<AlbumID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    playlist_uri_search = re.search(
        r'^spotify:playlist:(?P<PlaylistID>[0-9a-zA-Z]{22})$', search_input)
    playlist_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/playlist/(?P<PlaylistID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    episode_uri_search = re.search(
        r'^spotify:episode:(?P<EpisodeID>[0-9a-zA-Z]{22})$', search_input)
    episode_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/episode/(?P<EpisodeID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    show_uri_search = re.search(
        r'^spotify:show:(?P<ShowID>[0-9a-zA-Z]{22})$', search_input)
    show_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/show/(?P<ShowID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    artist_uri_search = re.search(
        r'^spotify:artist:(?P<ArtistID>[0-9a-zA-Z]{22})$', search_input)
    artist_url_search = re.search(
        r'^(https?://)?open\.spotify\.com/artist/(?P<ArtistID>[0-9a-zA-Z]{22})(\?si=.+?)?$',
        search_input,
    )

    if track_uri_search is not None or track_url_search is not None:
        track_id_str = (track_uri_search
                        if track_uri_search is not None else
                        track_url_search).group('TrackID')
    else:
        track_id_str = None

    if album_uri_search is not None or album_url_search is not None:
        album_id_str = (album_uri_search
                        if album_uri_search is not None else
                        album_url_search).group('AlbumID')
    else:
        album_id_str = None

    if playlist_uri_search is not None or playlist_url_search is not None:
        playlist_id_str = (playlist_uri_search
                           if playlist_uri_search is not None else
                           playlist_url_search).group('PlaylistID')
    else:
        playlist_id_str = None

    if episode_uri_search is not None or episode_url_search is not None:
        episode_id_str = (episode_uri_search
                          if episode_uri_search is not None else
                          episode_url_search).group('EpisodeID')
    else:
        episode_id_str = None

    if show_uri_search is not None or show_url_search is not None:
        show_id_str = (show_uri_search
                       if show_uri_search is not None else
                       show_url_search).group('ShowID')
    else:
        show_id_str = None

    if artist_uri_search is not None or artist_url_search is not None:
        artist_id_str = (artist_uri_search
                         if artist_uri_search is not None else
                         artist_url_search).group('ArtistID')
    else:
        artist_id_str = None

    return track_id_str, album_id_str, playlist_id_str, episode_id_str, show_id_str, artist_id_str

def get_song_info(spotifySession,song_id) -> tuple[list[str], list[any], str, str, any, any, any, any, any, any, int]:
    """ Retrieves metadata for downloaded songs """

    (raw, info) = invoke_url(spotifySession,f'{TRACKS_URL}?ids={song_id}&market=from_token')
    if not 'tracks' in info:
        raise ValueError(f'Invalid response from TRACKS_URL:\n{raw}')

    try:
        artists = []
        for data in info['tracks'][0]['artists']:
            artists.append(data['name'])

        album_name = info['tracks'][0]['album']['name']
        name = info['tracks'][0]['name']
        release_year = info['tracks'][0]['album']['release_date'].split('-')[0]
        disc_number = info['tracks'][0]['disc_number']
        track_number = info['tracks'][0]['track_number']
        scraped_song_id = info['tracks'][0]['id']
        is_playable = info['tracks'][0]['is_playable']
        duration_ms = info['tracks'][0]['duration_ms']

        image = info['tracks'][0]['album']['images'][0]
        for i in info['tracks'][0]['album']['images']:
            if i['width'] > image['width']:
                image = i
        image_url = image['url']

        return artists, info['tracks'][0]['artists'], album_name, name, image_url, release_year, disc_number, track_number, scraped_song_id, is_playable, duration_ms
    except Exception as e:
        raise ValueError(f'Failed to parse TRACKS_URL response: {str(e)}\n{raw}')

def get_playlist_songs(spotifySession,playlist_id):
    """ returns list of songs in a playlist """
    songs = []
    offset = 0
    limit = 100

    while True:
        resp = invoke_url_with_params(spotifySession,f'{PLAYLISTS_URL}/{playlist_id}/tracks', limit=limit, offset=offset)
        offset += limit
        songs.extend(resp['items'])
        if len(resp['items']) < limit:
            break

    return songs

def invoke_url(spotifySession, url, tryCount=0):
        headers = get_auth_header(spotifySession)
        response = requests.get(url, headers=headers)
        responsetext = response.text
        try:
            responsejson = response.json()
        except json.decoder.JSONDecodeError:
            responsejson = {"error": {"status": "unknown", "message": "received an empty response"}}

        if not responsejson or 'error' in responsejson:
            if tryCount < (3 - 1):
                logging.warning(f"Spotify API Error (try {tryCount + 1}) ({responsejson['error']['status']}): {responsejson['error']['message']}")
                time.sleep(5)
                return invoke_url(spotifySession,url, tryCount + 1)

            logging.error(f"Spotify API Error ({responsejson['error']['status']}): {responsejson['error']['message']}")

        return responsetext, responsejson

def invoke_url_with_params(spotifySession,url, limit, offset, **kwargs):
        headers, params = get_auth_header_and_params(spotifySession,limit=limit, offset=offset)
        params.update(kwargs)
        return requests.get(url, headers=headers, params=params).json()

def get_auth_token(spotifySession):
        return spotifySession.tokens().get_token(
            "user-read-email", "playlist-read-private", "user-library-read", "user-follow-read"
        ).access_token

def get_credentials_location():
    return os.path.join(args.data_path,"credentials.json")

def get_auth_header(spotifySession):
    return {
        'Authorization': f'Bearer {get_auth_token(spotifySession)}',
        'Accept-Language': 'en',
        'Accept': 'application/json',
        'app-platform': 'WebPlayer'
    }

def get_auth_header_and_params(spotifySession,limit, offset):
        return {
            'Authorization': f'Bearer {get_auth_token(spotifySession)}',
            'Accept-Language': 'en',
            'Accept': 'application/json',
            'app-platform': 'WebPlayer'
        }, {'limit': limit, 'offset': offset}

def fmt_seconds(secs: float) -> str:
    val = math.floor(secs)

    s = math.floor(val % 60)
    val -= s
    val /= 60

    m = math.floor(val % 60)
    val -= m
    val /= 60

    h = math.floor(val)

    if h == 0 and m == 0 and s == 0:
        return "0s"
    elif h == 0 and m == 0:
        return f'{s}s'.zfill(2)
    elif h == 0:
        return f'{m}'.zfill(2) + ':' + f'{s}'.zfill(2)
    else:
        return f'{h}'.zfill(2) + ':' + f'{m}'.zfill(2) + ':' + f'{s}'.zfill(2)

def get_content_stream(spotifySession, content_id, quality):
        return spotifySession.content_feeder().load(content_id, VorbisOnlyAudioQuality(quality), False, None)

def conv_artist_format(artists) -> str:
    """ Returns converted artist format """
    return ', '.join(artists)

def set_audio_tags(filename, artists, name, album_name, release_year, disc_number, track_number) -> None:
    """ sets music_tag metadata """
    tags = music_tag.load_file(filename)
    tags['albumartist'] = artists[0]
    tags['artist'] = conv_artist_format(artists)
    tags['tracktitle'] = name
    tags['album'] = album_name
    tags['year'] = release_year
    tags['discnumber'] = disc_number
    tags['tracknumber'] = track_number
    tags.save()

def set_music_thumbnail(filename, image_url) -> None:
    """ Downloads cover artwork """
    img = requests.get(image_url).content
    tags = music_tag.load_file(filename)
    tags['artwork'] = img
    tags.save()

def convert_audio_format(temp_filename,filename) -> None:
    """ Converts raw audio into playable file """
    file_codec = 'libmp3lame'
    if file_codec != 'copy':
        bitrate = '160k'
    else:
        bitrate = None

    output_params = ['-c:a', file_codec]
    if bitrate:
        output_params += ['-b:a', bitrate]

    try:
        ff_m = ffmpy.FFmpeg(
            global_options=['-y', '-hide_banner', '-loglevel error'],
            inputs={temp_filename: None},
            outputs={filename: output_params}
        )
        logging.debug("Converting file...")
        ff_m.run()

    except ffmpy.FFExecutableNotFoundError:
        logging.warning(f"Skipping {file_codec.upper()} conversion - ffmpeg not found!")

def main():

    try:
        # Create cache path if required
        if args.data_path is None:
            args.data_path = os.path.join(os.path.expanduser("~"), ".local", "share", "spoonie")
        if not os.path.exists(args.data_path):
            logging.info(f"Creating data folder {args.data_path}")
            os.makedirs(args.data_path)

        tonie_api = TonieAPI(args.tonie_username, args.tonie_password)
        household = next((x for x in tonie_api.get_households() if x.name == args.tonie_household), None)
        if household is None:
            raise ValueError(f"Tonie Household '{args.tonie_household}' not found!")
        creative_tonie = next((x for x in tonie_api.get_all_creative_tonies_by_household(household) if x.name == args.creative_tonie_name), None)
        if creative_tonie is None:
            raise ValueError(f"Creative Tonie '{args.creative_tonie_name}' not found!")
        
        cred_location = get_credentials_location()
        if Path(cred_location).is_file():
            try:
                conf = Session.Configuration.Builder().set_store_credentials(False).build()
                spotifySession = Session.Builder(conf).stored_file(cred_location).create()
            except RuntimeError:
                pass
        else:
            conf = Session.Configuration.Builder().set_stored_credential_file(cred_location).build()
            spotifySession= Session.Builder(conf).user_pass(args.spotify_username, args.spotify_password).create()

        track_id, album_id, playlist_id, episode_id, show_id, artist_id = regex_input_for_urls(args.playlist)

        if playlist_id is None:
            raise ValueError(f"Failed to parse playlist url")
        
        playlist_songs = get_playlist_songs(spotifySession,playlist_id)

        download_root = os.path.join(args.data_path,"download")

        if not os.path.exists(download_root):
            logging.info(f"Creating download folder {download_root}")
            os.makedirs(download_root)

        playlist_titles = {}
        playlist_song_lenghts = {}

        for song in playlist_songs:
            file_fullpath = ""
            download_tempfile = tempfile.NamedTemporaryFile(delete=False)

            try:
                track_id = song['track']['id']
                logging.info(f"Processing {song['track']['name']} (Id: {track_id})")
                (artists, raw_artists, album_name, name, image_url, release_year, disc_number,track_number, scraped_song_id, is_playable, duration_ms) = get_song_info(spotifySession,track_id)
                
                title = f"{artists[0]} - {name}"
                clean_title = fix_filename(title)
                filename = f"{clean_title}.mp3"
                file_fullpath = os.path.join(download_root,filename)

                playlist_titles[clean_title] = file_fullpath
                playlist_song_lenghts[clean_title] = (duration_ms / 1000)

                if not os.path.isfile(file_fullpath):
                    if(is_playable):
                        track = TrackId.from_base62(track_id)
                        stream = get_content_stream(spotifySession,track, AudioQuality.HIGH)
                        total_size = stream.input_stream.size
                        time_start = time.time()
                        downloaded = 0
                        b = 0
                        while b < 5:
                            data = stream.input_stream.stream().read(20000)
                            download_tempfile.write(data)
                            downloaded += len(data)
                            b += 1 if data == b'' else 0
                            if args.ban_protection:
                                delta_real = time.time() - time_start
                                delta_want = (downloaded / total_size) * (duration_ms/5000)
                                if delta_want > delta_real:
                                    time.sleep(delta_want - delta_real)
                        time_downloaded = time.time()
                        logging.info(f"Downloaded '{name}' in {fmt_seconds(time_downloaded - time_start)} seconds!")
                        logging.info("Finalizing file...")
                        convert_audio_format(download_tempfile.name,file_fullpath)
                        if os.path.isfile(file_fullpath):
                            set_audio_tags(file_fullpath, artists, name, album_name, release_year, disc_number, track_number)
                            set_music_thumbnail(file_fullpath,image_url)
                            logging.info("Done!")
                        else:
                            logging.error("Failed to finalize (convert) file!")
                    else:
                        logging.warning(f"'{filename}' is not playable => Skipping!")
                else:
                    logging.info(f"Skipping '{filename}' => already exists")
            except Exception as ex:
                logging.error(f"Failed to download song {song['track']['name']}")
                logging.critical(ex, exc_info=True)
            finally:
                download_tempfile.close()
                if os.path.exists(download_tempfile.name):
                    os.unlink(download_tempfile.name)
        logging.info("Playlist download completed!")

        logging.info("Removing orphaned chapters from creative tonie...")
        chapters_removed = False
        chapters = creative_tonie.chapters
        for chapter in chapters:
            foundOnPlaylist = next((x for x in playlist_titles.keys() if x == chapter.title), None)
            if foundOnPlaylist is None:
                logging.info(f"Removing chapter '{chapter.title}' from creative tonie cause its not longer on the playlist")
                chapters.remove(chapter)
                chapters_removed = True
        if chapters_removed:
            tonie_api.sort_chapter_of_tonie(creative_tonie,chapters)

        # Refresh tonie
        creative_tonie = next((x for x in tonie_api.get_all_creative_tonies_by_household(household) if x.name == args.creative_tonie_name), None)

        logging.info("Uploading new songs / chapters...")
        tonie_seconds_remaining = creative_tonie.secondsRemaining
        for key, value in playlist_titles.items():
            foundOnCreativeTonie = next((x for x in chapters if x.title == key), None)
            if foundOnCreativeTonie is None:
                song_playtime = playlist_song_lenghts[key]
                if tonie_seconds_remaining - song_playtime > 0:
                  logging.info(f"Uploading '{key}' to  creative tonie...")
                  tonie_api.upload_file_to_tonie(creative_tonie,value,key)
                  tonie_seconds_remaining = tonie_seconds_remaining - song_playtime
                  logging.info(f"Upload complete! => {tonie_seconds_remaining} free seconds remaining on creative tonie")
                else:
                  logging.warning(f" Skipping {key} => Not enough free space on creative tonie! Needed: {song_playtime}s | Free: {tonie_seconds_remaining}s")
            else:
                logging.info(f"Skipping '{key}' => already present on creative tonie")                
        
        # Refresh tonie
        creative_tonie = next((x for x in tonie_api.get_all_creative_tonies_by_household(household) if x.name == args.creative_tonie_name), None)
        chapters = creative_tonie.chapters

        logging.info("Sorting chapters...")
        chapters_sorted = False
        for num, name in enumerate(playlist_titles.keys()):
            oldchapterIndex = next((i for i, item in enumerate(chapters) if item.title == name), -1)
            if oldchapterIndex != -1 and num != oldchapterIndex:
                chapters.insert(num, chapters.pop(oldchapterIndex))
                chapters_sorted = True
        if chapters_sorted:
            logging.info("sorting changed...")
            tonie_api.sort_chapter_of_tonie(creative_tonie,chapters)

    except Exception as ex:
        logging.critical(ex, exc_info=True)
        sys.exit(-1)

if __name__ == '__main__':
    main()