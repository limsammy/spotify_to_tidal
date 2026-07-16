from spotipy import Spotify
from tidalapi import Session, Track

from .config import PlaylistConfig, SpotifyConfig, SyncConfig, TidalConfig
from .spotify import SpotifyTrack

TidalID = str
SpotifyID = str
TidalSession = Session
TidalTrack = Track
SpotifySession = Spotify

__all__ = [
    "PlaylistConfig",
    "SpotifyConfig",
    "SpotifyID",
    "SpotifySession",
    "SpotifyTrack",
    "SyncConfig",
    "TidalConfig",
    "TidalID",
    "TidalPlaylist",
    "TidalSession",
    "TidalTrack",
]
