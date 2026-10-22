# !/usr/bin/env python3

import logging
import requests
import re
import json
import os
import sys
import time
import math
import music_tag
import tempfile
import ffmpy

from typing import Optional
from pathlib import Path
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.core import Session, OAuth, MercuryRequests
from librespot.metadata import TrackId, EpisodeId, PlaylistId, ShowId
from tonie_api.api import TonieAPI
from tonie_api.models import Config, CreativeTonie, User

from argparse import ArgumentParser

IMAGE_URL_PREFIX = 'https://i.scdn.co/image/'
OAUTH_REDIRECT_URL = 'http://127.0.0.1:4381/login'

usage = """
""".format(sys.version, os.path.basename(__file__))

parser = ArgumentParser(usage=usage)
parser.add_argument("-su", "--spotify-username", dest="spotify_username", required=False, help="No longer used, see README how to login to spotify", deprecated=True)
parser.add_argument("-sp", "--spotify-password", dest="spotify_password", required=False, help="No longer used, see README how to login to spotify", deprecated=True)
parser.add_argument("-tu", "--tonie-username", dest="tonie_username", required=True, help="")
parser.add_argument("-tp", "--tonie-password", dest="tonie_password", required=True, help="")
parser.add_argument("-th", "--tonie-household", dest="tonie_household", required=True, help="Name of the 'meine Tonies' Haushalt")
parser.add_argument("-ctn", "--creative-tonie", dest="creative_tonie_name", required=True, help="Name of the creative tonie")
parser.add_argument("-tt", "--tonie-timeout", default=30,type=int, dest="tonie_timeout", required=False, help="Set timeout for tonieapi (which is quite slow sometimes)")
parser.add_argument("-P", "--playlist", dest="playlist", required=True, help="Link of a Spotify playlist or a show/podcast")
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

def regex_input_for_urls(search_input) -> tuple[Optional[str], Optional[str]]:
    """ Extracts the playlist / show id from a spotify url or uri (e.g. open.spotify.com/intl-de/playlist/<id>?si=... or spotify:show:<id>) """
    playlist_search = re.search(r'playlist[:/](?P<PlaylistID>[0-9a-zA-Z]{22})', search_input)
    show_search = re.search(r'show[:/](?P<ShowID>[0-9a-zA-Z]{22})', search_input)

    playlist_id_str = playlist_search.group('PlaylistID') if playlist_search is not None else None
    show_id_str = show_search.group('ShowID') if show_search is not None else None

    return playlist_id_str, show_id_str

def get_cover_url(image_group) -> Optional[str]:
    """ Returns the url of the largest image of an ImageGroup """
    if not image_group.image:
        return None
    image = max(image_group.image, key=lambda i: (i.width, i.size))
    return IMAGE_URL_PREFIX + image.file_id.hex()

def get_episode_info(spotifySession, episode_id_str) -> tuple[str, int, str]:
    """ Retrieves metadata for podcast episodes """
    episode = spotifySession.api().get_metadata_4_episode(EpisodeId.from_base62(episode_id_str))
    return fix_filename(episode.show.name), episode.duration, fix_filename(episode.name)

def get_song_info(spotifySession, song_id) -> tuple[list[str], str, str, Optional[str], Optional[int], int, int, bool, int]:
    """ Retrieves metadata for downloaded songs """
    track = spotifySession.api().get_metadata_4_track(TrackId.from_base62(song_id))

    artists = [artist.name for artist in track.artist]
    album_name = track.album.name
    name = track.name
    release_year = track.album.date.year or None
    disc_number = track.disc_number
    track_number = track.number
    # same check as librespot uses to pick a playable (alternative) version of the track
    is_playable = len(track.file) > 0 or any(len(alternative.file) > 0 for alternative in track.alternative)
    duration_ms = track.duration
    image_url = get_cover_url(track.album.cover_group)

    return artists, album_name, name, image_url, release_year, disc_number, track_number, is_playable, duration_ms

def get_show_episodes(spotifySession, show_id_str) -> list[str]:
    """ returns the ids of all episodes of a show """
    show = spotifySession.api().get_metadata_4_show(ShowId.from_base62(show_id_str))
    if not show.episode:
        raise ValueError(f"Spotify returned no episodes for show '{show.name}' (Id: {show_id_str})")
    return [EpisodeId.from_hex(episode.gid.hex()).id() for episode in show.episode]

def get_playlist_items(spotifySession, playlist_id) -> list[str]:
    """ returns the uris of all items (tracks / episodes) in a playlist """
    playlist = spotifySession.api().get_playlist(PlaylistId.from_base62(playlist_id))
    items = [item.uri for item in playlist.contents.items]
    if playlist.contents.truncated:
        logging.warning(f"Spotify returned only the first {len(items)} of {playlist.length} playlist items => the remaining items are ignored")
    return items

def get_credentials_location():
    return os.path.join(args.data_path,"credentials.json")

def save_credentials(spotifySession) -> None:
    """ Stores the reusable credentials of the session, so further runs don't need an OAuth login """
    cred_location = get_credentials_location()
    with open(f"{cred_location}.tmp", "w") as f:
        json.dump(spotifySession.credentials(), f)
    os.replace(f"{cred_location}.tmp", cred_location)

def spotify_oauth_login(conf) -> Session:
    def print_login_url(url):
        logging.warning(f"No spotify credentials found ({get_credentials_location()}) => Please login to spotify:")
        logging.warning(f"1. Open the following link in your browser and login: {url}")
        logging.warning(f"2. Spotify then redirects your browser to {OAUTH_REDIRECT_URL}?code=... - spoonie is waiting for this request.")
        logging.warning("   If the page can't be loaded (e.g. spoonie runs on another machine), copy the url from your browser and open it on the machine spoonie runs on, e.g. with curl.")

    # listen on all interfaces, so the callback also reaches spoonie inside docker
    oauth = OAuth(MercuryRequests.keymaster_client_id, OAUTH_REDIRECT_URL, print_login_url).set_listen_all(True)
    builder = Session.Builder(conf)
    builder.login_credentials = oauth.flow()
    return builder.create()

def spotify_login() -> Session:
    conf = Session.Configuration.Builder().set_store_credentials(False).build()

    # No OAuth fallback if stored credentials fail: a network error would otherwise block every cron run waiting for a login
    cred_location = get_credentials_location()
    if Path(cred_location).is_file():
        try:
            spotifySession = Session.Builder(conf).stored_file(cred_location).create()
        except Exception as ex:
            raise RuntimeError(f"Spotify login with '{cred_location}' failed. If the credentials are no longer valid, delete this file to login again.") from ex
    else:
        spotifySession = spotify_oauth_login(conf)

    save_credentials(spotifySession)
    logging.info(f"Logged in to spotify as '{spotifySession.username()}'")
    return spotifySession

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

def downloadSpotifyTrack(spotifySession, name, track, track_duration_ms, download_tempfile, file_fullpath):
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
            delta_want = (downloaded / total_size) * (track_duration_ms/5000)
            if delta_want > delta_real:
                time.sleep(delta_want - delta_real)
    time_downloaded = time.time()
    logging.info(f"Downloaded '{name}' in {fmt_seconds(time_downloaded - time_start)} seconds!")

def trim_to_128(s: str) -> str:
    return s[:128]

def main():

    try:
        # Create cache path if required
        if args.data_path is None:
            args.data_path = os.path.join(os.path.expanduser("~"), ".local", "share", "spoonie")
        if not os.path.exists(args.data_path):
            logging.info(f"Creating data folder {args.data_path}")
            os.makedirs(args.data_path)

        # Login to spotify first, as the OAuth login may wait for the user
        spotifySession = spotify_login()

        tonie_api = TonieAPI(args.tonie_username, args.tonie_password, args.tonie_timeout)
        household = next((x for x in tonie_api.get_households() if x.name == args.tonie_household), None)
        if household is None:
            raise ValueError(f"Tonie Household '{args.tonie_household}' not found!")
        creative_tonie = next((x for x in tonie_api.get_all_creative_tonies_by_household(household) if x.name == args.creative_tonie_name), None)
        if creative_tonie is None:
            raise ValueError(f"Creative Tonie '{args.creative_tonie_name}' not found!")

        playlist_id, show_id = regex_input_for_urls(args.playlist)

        if playlist_id is None and show_id is None:
            raise ValueError("Supplied playlist is neither a valid playlist or show")

        show_episodes = []
        playlist_songs = []

        download_root = os.path.join(args.data_path,"download")

        if not os.path.exists(download_root):
            logging.info(f"Creating download folder {download_root}")
            os.makedirs(download_root)

        download_titles = {}
        download_title_lenghts = {}
        failed_items = 0

        if playlist_id is not None:
            for item_uri in get_playlist_items(spotifySession,playlist_id):
                item_type, item_id = item_uri.split(":")[1:3]
                if item_type == "track":
                    playlist_songs.append(item_id)
                elif item_type == "episode":
                    logging.info(f"Playlist track with Id {item_id} seems to be an podcast episode => adding to episode to process later")
                    show_episodes.append(item_id)
                else:
                    logging.warning(f"Skipping playlist item '{item_uri}' => unsupported type '{item_type}'")

        if show_id is not None:
            show_episodes.extend(get_show_episodes(spotifySession,show_id))

        if (playlist_songs is not None):

            for track_id in playlist_songs:

                file_fullpath = ""
                download_tempfile = tempfile.NamedTemporaryFile(delete=False)

                try:

                    (artists, album_name, name, image_url, release_year, disc_number,track_number, is_playable, duration_ms) = get_song_info(spotifySession,track_id)
                    logging.info(f"Processing {name} (Id: {track_id})")

                    title = f"{artists[0]} - {name}"
                    clean_title = trim_to_128(fix_filename(title))
                    filename = f"{clean_title}.mp3"
                    file_fullpath = os.path.join(download_root,filename)

                    if not os.path.isfile(file_fullpath):
                        if(is_playable):
                            track = TrackId.from_base62(track_id)
                            downloadSpotifyTrack(spotifySession,clean_title,track,duration_ms,download_tempfile,file_fullpath)
                            logging.info("Finalizing file...")
                            convert_audio_format(download_tempfile.name,file_fullpath)
                            if os.path.isfile(file_fullpath):
                                logging.info("Done!")
                                logging.info("Setting track metadata...")
                                set_audio_tags(file_fullpath, artists, name, album_name, release_year, disc_number, track_number)
                                if image_url:
                                    set_music_thumbnail(file_fullpath,image_url)
                                logging.info("Done!")

                                download_titles[clean_title] = file_fullpath
                                download_title_lenghts[clean_title] = (duration_ms / 1000)
                            else:
                                logging.error("Failed to finalize (convert) file!")
                        else:
                            logging.warning(f"'{filename}' is not playable => Skipping!")
                    else:
                        logging.info(f"Skipping '{filename}' => already exists")

                        download_titles[clean_title] = file_fullpath
                        download_title_lenghts[clean_title] = (duration_ms / 1000)

                except Exception as ex:
                    failed_items += 1
                    logging.error(f"Failed to download song with Id {track_id}")
                    logging.critical(ex, exc_info=True)
                finally:
                    download_tempfile.close()
                    if os.path.exists(download_tempfile.name):
                        os.unlink(download_tempfile.name)
            logging.info("Playlist download completed!")

        if (show_episodes is not None):

            for episode in show_episodes:

                file_fullpath = ""
                download_tempfile = tempfile.NamedTemporaryFile(delete=False)

                try:

                    logging.info(f"Processing episode with id {episode}")
                    podcast_name, duration_ms, episode_name = get_episode_info(spotifySession, episode)
                    title = f"{podcast_name} - {episode_name}"

                    clean_title = trim_to_128(fix_filename(title))
                    filename = f"{clean_title}.mp3"
                    file_fullpath = os.path.join(download_root,filename)

                    if not os.path.isfile(file_fullpath):
                        # librespot also handles externally hosted episodes
                        track = EpisodeId.from_base62(episode)
                        downloadSpotifyTrack(spotifySession,clean_title,track,duration_ms,download_tempfile,file_fullpath)
                        logging.info("Finalizing file...")
                        convert_audio_format(download_tempfile.name,file_fullpath)
                        if os.path.isfile(file_fullpath):

                            logging.info("Done!")
                            download_titles[clean_title] = file_fullpath
                            download_title_lenghts[clean_title] = (duration_ms / 1000)
                        else:
                            logging.error("Failed to finalize (convert) file!")
                    else:
                        logging.info(f"Skipping '{filename}' => already exists")

                        download_titles[clean_title] = file_fullpath
                        download_title_lenghts[clean_title] = (duration_ms / 1000)

                except Exception as ex:
                    failed_items += 1
                    logging.error(f"Failed to download episode with id {episode}")
                    logging.critical(ex, exc_info=True)
                finally:
                    download_tempfile.close()
                    if os.path.exists(download_tempfile.name):
                        os.unlink(download_tempfile.name)
            logging.info("Show download completed!")

        # Don't wipe the creative tonie if spotify failed for every item (e.g. API changes)
        if failed_items > 0 and not download_titles:
            raise ValueError(f"Failed to process all {failed_items} playlist / show items => leaving creative tonie untouched")

        logging.info("Removing orphaned chapters from creative tonie...")
        chapters_removed = False
        chapters = creative_tonie.chapters
        for chapter in chapters:
            foundOnPlaylist = next((x for x in download_titles.keys() if x == chapter.title), None)
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
        for key, value in download_titles.items():
            foundOnCreativeTonie = next((x for x in chapters if x.title == key), None)
            if foundOnCreativeTonie is None:
                song_playtime = download_title_lenghts[key]
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
        for num, name in enumerate(download_titles.keys()):
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
