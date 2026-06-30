import asyncio
import math
import time
from typing import List
import requests
import tidalapi
from tqdm import tqdm
from tqdm.asyncio import tqdm as atqdm

def _remove_indices_from_playlist(playlist: tidalapi.UserPlaylist, indices: List[int], attempts: int=5):
    index_string = ",".join(map(str, indices))
    url = (playlist._base_url + '/items/%s') % (playlist.id, index_string)
    for attempt in range(attempts):
        # only send the If-None-Match precondition when we have a current ETag (matches tidalapi)
        headers = {'If-None-Match': playlist._etag} if playlist._etag else None
        try:
            playlist.request.request('DELETE', url, headers=headers)
            break
        except requests.exceptions.HTTPError as e:
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            if status == 412 and attempt < attempts - 1:
                # Tidal serves a stale ETag between consecutive writes; refresh it and retry the chunk
                time.sleep(1 + attempt)
                playlist._reparse()
                continue
            raise
    playlist._reparse()

def clear_tidal_playlist(playlist: tidalapi.UserPlaylist, chunk_size: int=20):
    # Refresh the playlist so its ETag matches Tidal's current state. The custom chunk fetcher used to
    # load playlist tracks doesn't populate _etag, so without this the first DELETE sends a stale (or
    # missing) If-None-Match precondition and Tidal rejects it with 412 Precondition Failed.
    playlist._reparse()
    with tqdm(desc="Erasing existing tracks from Tidal playlist", total=playlist.num_tracks) as progress:
        while playlist.num_tracks:
            indices = range(min(playlist.num_tracks, chunk_size))
            _remove_indices_from_playlist(playlist, indices)
            progress.update(len(indices))
    
async def _get_all_chunks(url, session, parser, params={}) -> List[tidalapi.Track]:
    """ 
        Helper function to get all items from a Tidal endpoint in parallel
        The main library doesn't provide the total number of items or expose the raw json, so use this wrapper instead
    """
    def _make_request(offset: int=0):
        new_params = params
        new_params['offset'] = offset
        return session.request.map_request(url, params=new_params)

    first_chunk_raw = _make_request()
    limit = first_chunk_raw['limit']
    total = first_chunk_raw['totalNumberOfItems']
    items = session.request.map_json(first_chunk_raw, parse=parser)

    if len(items) < total:
        offsets = [limit * n for n in range(1, math.ceil(total/limit))]
        extra_results = await atqdm.gather(
                *[asyncio.to_thread(lambda offset: session.request.map_json(_make_request(offset), parse=parser), offset) for offset in offsets],
            desc="Fetching additional data chunks"
        )
        for extra_result in extra_results:
            items.extend(extra_result)
    return items

async def get_all_favorites(favorites: tidalapi.Favorites, order: str = "NAME", order_direction: str = "ASC", chunk_size: int=100) -> List[tidalapi.Track]:
    """ Get all favorites from Tidal playlist in chunks """
    params = {
        "limit": chunk_size,
        "order": order,
        "orderDirection": order_direction,
    }
    return await _get_all_chunks(f"{favorites.base_url}/tracks", session=favorites.session, parser=favorites.session.parse_track, params=params)

async def get_all_playlists(user: tidalapi.User, chunk_size: int=10) -> List[tidalapi.Playlist]:
    """ Get all user playlists from Tidal in chunks """
    print(f"Loading playlists from Tidal user")
    params = {
        "limit": chunk_size,
    }
    return await _get_all_chunks(f"users/{user.id}/playlists", session=user.session, parser=user.playlist.parse_factory, params=params)

async def get_all_playlist_tracks(playlist: tidalapi.Playlist, chunk_size: int=20) -> List[tidalapi.Track]:
    """ Get all tracks from Tidal playlist in chunks """
    params = {
        "limit": chunk_size,
    }
    print(f"Loading tracks from Tidal playlist '{playlist.name}'")
    return await _get_all_chunks(f"{playlist._base_url%playlist.id}/tracks", session=playlist.session, parser=playlist.session.parse_track, params=params)

async def get_all_saved_albums(user: tidalapi.User) -> List[tidalapi.Album]:
    """ Get all saved albums from Tidal user favorites """
    print(f"Loading saved albums from Tidal")
    return await asyncio.to_thread(user.favorites.albums_paginated)

def add_album_to_tidal_collection(session: tidalapi.Session, album_id: str):
    """ Add album to user's Tidal favorites """
    return session.user.favorites.add_album(album_id)

async def get_all_saved_artists(user: tidalapi.User) -> List[tidalapi.Artist]:
    """ Get all followed artists from Tidal user favorites """
    print(f"Loading followed artists from Tidal")
    return await asyncio.to_thread(user.favorites.artists_paginated)

def add_artist_to_tidal_collection(session: tidalapi.Session, artist_id: str):
    """ Add artist to user's Tidal favorites """
    return session.user.favorites.add_artist(artist_id)

