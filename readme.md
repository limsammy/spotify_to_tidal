# spotify_to_tidal (modified)

> **Note:** This is a modified version of [spotify2tidal/spotify_to_tidal](https://github.com/spotify2tidal/spotify_to_tidal) with the following changes:
>
> - **uv integration** — the project is run with [uv](https://docs.astral.sh/uv/); no manual venv or pip install needed.
> - **Interactive track matching** — when the automatic search can't find a track on Tidal, you're shown up to 5 candidate matches and can pick one (`1-5`) or skip (`s`), instead of the track silently being left out.
> - **`--remove-tracks` flag** — remove all tracks from a given Spotify album (or a single track) from both the Spotify playlist and its Tidal counterpart in one command.

A command line tool for importing your Spotify playlists into Tidal. Due to various performance optimisations, it is particularly suited to periodic synchronisation of large collections.

Installation
------------
Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then clone this git repository. That's it — `uv run` resolves dependencies and installs the package automatically on first use.

Setup
-----
0. Copy the file example_config.yml to config.yml
0. Go [here](https://developer.spotify.com/documentation/general/guides/authorization/app-settings/) and register a new app on developer.spotify.com.
0. Copy and paste the client ID and client secret to the Spotify part of the config file
0. Copy the value in 'redirect_uri' of the config file to the Redirect URIs field on developer.spotify.com and press ADD
0. Enter your Spotify username in the config file

Usage
-----
To synchronize all your Spotify playlists with your Tidal account, run from the project root directory:

```bash
uv run spotify_to_tidal
```

You can also just synchronize a specific playlist:

```bash
uv run spotify_to_tidal --uri 1ABCDEqsABCD6EaABCDa0a # accepts playlist id or full playlist uri
```

Or sync just the 'Liked Songs' with:

```bash
uv run spotify_to_tidal --sync-favorites
```

See example_config.yml for more configuration options and `uv run spotify_to_tidal --help` for all command line options.

### Interactive matching of missing tracks

When a playlist sync finishes searching, any track that couldn't be matched automatically triggers an interactive prompt (only when running in a terminal). For each unmatched track you get a list of Tidal candidates with artist, title, album and duration:

```
Spotify: Pretenders - My City Was Gone (185s)
  1. Pretenders - My City Was Gone [Learning To Crawl] (184s)
  2. ...
Pick a match [1-5] or s(kip):
```

Pick a number to add that track to the Tidal playlist, or `s` (or just Enter) to skip it. Manual picks are stored in `.cache.db`, so future re-syncs reuse them without prompting again (skipped tracks are re-asked).

### Removing tracks from both playlists

To remove tracks from a playlist on both Spotify and Tidal, use `--remove-tracks` together with `--uri`. The value is always a **Spotify** ID — the Tidal side is updated by the sync that follows, so no Tidal IDs are ever needed:

```bash
# remove every track from a Spotify album
uv run spotify_to_tidal --uri <playlist_id> --remove-tracks 'album:<spotify_album_id>'

# remove a single track
uv run spotify_to_tidal --uri <playlist_id> --remove-tracks 'track:<spotify_track_id>'
```

The matching tracks are listed and you're asked to confirm before anything is removed from Spotify. The sync then rewrites the Tidal playlist to mirror Spotify, which drops the tracks there too. (This also means any track you remove from a playlist directly in Spotify is removed from Tidal on the next sync.)

Removal requires the `playlist-modify-public` and `playlist-modify-private` Spotify scopes, so the first run after upgrading will re-open the browser to re-authorize.

---

#### Join our amazing community as a code contributor
<br><br>
<a href="https://github.com/spotify2tidal/spotify_to_tidal/graphs/contributors">
  <img class="dark-light" src="https://contrib.rocks/image?repo=spotify2tidal/spotify_to_tidal&anon=0&columns=25&max=100&r=true" />
</a>
