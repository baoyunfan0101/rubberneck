from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from threading import RLock

from .base import PipelineResult
from .registry import PIPELINES

log = logging.getLogger(__name__)

_TYPE_MAP: dict[type, str] = {
    int: 'INTEGER',
    float: 'REAL',
    bool: 'INTEGER',
    bytes: 'BLOB',
}


def _sqlite_type(value: object) -> str:
    for python_type, sql_type in _TYPE_MAP.items():
        if isinstance(value, python_type):
            return sql_type
    return 'TEXT'


@PIPELINES.register('sqlite')
class SQLitePipeline:

    def __init__(
        self,
        table: str,
        *,
        path: str = './data',
        filename: str = 'rubberneck_pipeline.db',
        unique_on: tuple[str, ...] | None = None,
        on_conflict: str = 'IGNORE',
    ) -> None:
        self.table = table
        self.unique_on = unique_on
        self.on_conflict = on_conflict.upper()

        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        self.db_path = directory / filename

        self._lock = RLock()
        self._conn: sqlite3.Connection | None = None
        self._columns: set[str] = set()  # known column names

    def open(self) -> None:
        self._conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._conn.execute('PRAGMA synchronous=NORMAL')
        self._conn.execute('PRAGMA busy_timeout=30000')

        self._columns = self._load_columns()  # load existing columns

    def process_item(self, item: Mapping[str, object]) -> PipelineResult:
        if not item:
            return ()

        self._ensure_table(item)
        self._insert(item)
        return ()

    def close(self) -> None:
        if self._conn is not None:
            with self._lock:
                self._conn.execute('PRAGMA wal_checkpoint(FULL)')
                self._conn.close()
                self._conn = None

    def _load_columns(self) -> set[str]:
        assert self._conn is not None
        try:
            cursor = self._conn.execute(f'PRAGMA table_info({self.table})')
            return {row[1] for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            return set()

    def _ensure_table(self, item: Mapping[str, object]) -> None:
        assert self._conn is not None

        new_keys = set(item.keys()) - self._columns

        if not new_keys and self._columns:
            return  # table already has every column we need

        with self._lock:
            if not self._columns:
                # first time — create the table
                col_defs = ', '.join(
                    f'{k} {_sqlite_type(item[k])}'
                    for k in item
                )
                constraints = ''
                if self.unique_on:
                    unique_cols = ', '.join(self.unique_on)
                    constraints = f', UNIQUE ({unique_cols})'
                self._conn.execute(
                    f'CREATE TABLE IF NOT EXISTS {self.table} ({col_defs}{constraints})'
                )
                self._columns = set(item.keys())
                log.debug('created table %s with columns %s', self.table, self._columns)
            else:
                # add missing columns
                for key in new_keys:
                    sql_type = _sqlite_type(item[key])
                    self._conn.execute(
                        f'ALTER TABLE {self.table} ADD COLUMN {key} {sql_type}'
                    )
                    self._columns.add(key)
                    log.debug('added column %s %s to %s', key, sql_type, self.table)

    def _insert(self, item: Mapping[str, object]) -> None:
        assert self._conn is not None

        columns = list(item.keys())
        placeholders = ', '.join('?' for _ in columns)
        col_names = ', '.join(columns)

        sql = (
            f'INSERT OR {self.on_conflict} INTO {self.table} '
            f'({col_names}) VALUES ({placeholders})'
        )

        with self._lock:
            self._conn.execute(sql, [item[c] for c in columns])
