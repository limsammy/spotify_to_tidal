import datetime
import sqlalchemy
from sqlalchemy import Table, Column, String, Integer, DateTime, MetaData, insert, select, update, delete
from typing import Dict, List, Sequence, Set, Mapping


class MatchFailureDatabase:
    """ 
    sqlite database of match failures which persists between runs
    this can be used concurrently between multiple processes
    """

    def __init__(self, filename='.cache.db'):
        self.engine = sqlalchemy.create_engine(f"sqlite:///{filename}")
        meta = MetaData()
        self.match_failures = Table('match_failures', meta,
                                    Column('track_id', String,
                                           primary_key=True),
                                    Column('insert_time', DateTime),
                                    Column('next_retry', DateTime),
                                    sqlite_autoincrement=False)
        meta.create_all(self.engine)

    def _get_next_retry_time(self, insert_time: datetime.datetime | None = None) -> datetime.datetime:
        if insert_time:
            # double interval on each retry
            interval = 2 * (datetime.datetime.now() - insert_time)
        else:
            interval = datetime.timedelta(days=7)
        return datetime.datetime.now() + interval

    def cache_match_failure(self, track_id: str):
        """ notifies that matching failed for the given track_id """
        fetch_statement = select(self.match_failures).where(
            self.match_failures.c.track_id == track_id)
        with self.engine.connect() as connection:
            with connection.begin():
                # Either update the next_retry time if track_id already exists, otherwise create a new entry
                existing_failure = connection.execute(
                    fetch_statement).fetchone()
                if existing_failure:
                    update_statement = update(self.match_failures).where(
                        self.match_failures.c.track_id == track_id).values(next_retry=self._get_next_retry_time())
                    connection.execute(update_statement)
                else:
                    connection.execute(insert(self.match_failures), {
                                       "track_id": track_id, "insert_time": datetime.datetime.now(), "next_retry": self._get_next_retry_time()})

    def has_match_failure(self, track_id: str) -> bool:
        """ checks if there was a recent search for which matching failed with the given track_id """
        statement = select(self.match_failures.c.next_retry).where(
            self.match_failures.c.track_id == track_id)
        with self.engine.connect() as connection:
            match_failure = connection.execute(statement).fetchone()
            if match_failure:
                return match_failure.next_retry > datetime.datetime.now()
            return False

    def remove_match_failure(self, track_id: str):
        """ removes match failure from the database """
        statement = delete(self.match_failures).where(
            self.match_failures.c.track_id == track_id)
        with self.engine.connect() as connection:
            with connection.begin():
                connection.execute(statement)


class TrackMatchCache:
    """
    Non-persistent mapping of spotify ids -> tidal_ids
    This should NOT be accessed concurrently from multiple processes
    """
    data: Dict[str, int] = {}

    def get(self, track_id: str) -> int | None:
        return self.data.get(track_id, None)

    def insert(self, mapping: tuple[str, int]):
        self.data[mapping[0]] = mapping[1]


class ManualMatchDatabase:
    """
    sqlite mapping of spotify track id -> tidal track id, persisting manually confirmed matches between runs
    """

    def __init__(self, filename='.cache.db'):
        self.engine = sqlalchemy.create_engine(f"sqlite:///{filename}")
        meta = MetaData()
        self.matches = Table('manual_matches', meta,
                             Column('spotify_id', String, primary_key=True),
                             Column('tidal_id', Integer),
                             sqlite_autoincrement=False)
        meta.create_all(self.engine)

    def get(self, spotify_id: str) -> int | None:
        statement = select(self.matches.c.tidal_id).where(
            self.matches.c.spotify_id == spotify_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).fetchone()
            return row.tidal_id if row else None

    def insert(self, spotify_id: str, tidal_id: int):
        with self.engine.connect() as connection:
            with connection.begin():
                connection.execute(delete(self.matches).where(
                    self.matches.c.spotify_id == spotify_id))
                connection.execute(insert(self.matches), {
                                   "spotify_id": spotify_id, "tidal_id": tidal_id})


# Main singleton instance
failure_cache = MatchFailureDatabase()
track_match_cache = TrackMatchCache()
manual_match_cache = ManualMatchDatabase()
