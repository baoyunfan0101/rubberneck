from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from threading import RLock

from ..model import Request
from .codec import JsonRequestCodec, RequestCodec
from .registry import SCHEDULERS

PENDING = 'PENDING'
LEASED = 'LEASED'
DONE = 'DONE'
FAILED = 'FAILED'


@SCHEDULERS.register('sqlite')
class SQLiteScheduler:
    def __init__(
        self,
        path: str = './data',
        filename: str = 'rubberneck.db',
        reset: bool = False,
        codec: RequestCodec | None = None,
    ) -> None:
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        self.db_path = directory / filename
        self.codec = codec or JsonRequestCodec()  # encode/decode Request
        self._lock = RLock()  # allow nested lock acquisition by the same thread
        self._conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,  # manually control transactions and database locks
            check_same_thread=False,  # allow non-creator threads to use
        )
        self._conn.execute('PRAGMA journal_mode=WAL')  # WAL: allow reading while another thread is writing
        self._conn.execute('PRAGMA synchronous=NORMAL')  # NORMAL: reduce disk synchronization frequency
        self._conn.execute('PRAGMA busy_timeout=30000')  # wait 30000ms when db is locked
        if reset:
            self._conn.execute('DROP TABLE IF EXISTS request_queue')
        self._init()
        self._recover()

    def open(self) -> None:
        pass

    def enqueue(self, request: Request) -> bool:
        payload = self.codec.encode(request)
        fingerprint = self._fingerprint(request)
        with self._lock:  # lock the connection
            cursor = self._conn.execute(
                '''
                INSERT OR IGNORE INTO request_queue
                    (fingerprint, payload, priority, status)
                VALUES (?, ?, ?, ?)
                ''',
                (fingerprint, payload, request.priority, PENDING),
            )
            return cursor.rowcount == 1

    def dequeue(self) -> Request | None:
        with self._lock:
            self._conn.execute('BEGIN IMMEDIATE')  # start a transaction and acquire a write lock
            try:
                row = self._conn.execute(
                    '''
                    SELECT fingerprint, payload
                    FROM request_queue
                    WHERE status = ?
                    ORDER BY priority DESC, sequence ASC
                    LIMIT 1
                    ''',
                    (PENDING,),
                ).fetchone()
                if row is None:
                    self._conn.commit()  # persist changes and release the lock
                    return None
                self._conn.execute(
                    '''
                    UPDATE request_queue
                    SET status = ?, error = NULL
                    WHERE fingerprint = ?
                    ''',
                    (LEASED, row[0]),
                )
                self._conn.commit()
                return self.codec.decode(row[1])
            except Exception:
                self._conn.rollback()  # roll back the transaction on error
                raise  # re-raise the original exception

    def mark_done(self, request: Request) -> None:
        self._transition(request, DONE, None)

    def mark_failed(self, request: Request, error: Exception) -> None:
        self._transition(request, FAILED, str(error))

    def has_pending(self) -> bool:
        return self.pending_count() > 0

    def pending_count(self) -> int:
        return self._count(PENDING)

    def leased_count(self) -> int:
        return self._count(LEASED)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init(self) -> None:
        self._conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS request_queue (
                sequence INTEGER PRIMARY KEY,
                fingerprint TEXT UNIQUE NOT NULL,
                payload TEXT NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                error TEXT
            )
            '''
        )  # fingerprint must be unique
        self._conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_request_queue_status_priority
            ON request_queue(status, priority DESC, sequence ASC)
            '''
        )

    def _recover(self) -> None:
        self._conn.execute(
            'UPDATE request_queue SET status = ? WHERE status = ?',
            (PENDING, LEASED),
        )

    def _transition(self, request: Request, status: str, error: str | None) -> None:
        with self._lock:
            cursor = self._conn.execute(
                '''
                UPDATE request_queue
                SET status = ?, error = ?
                WHERE fingerprint = ? AND status = ?
                ''',
                (status, error, self._fingerprint(request), LEASED),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f'request is not leased: {request.url}')

    def _count(self, status: str) -> int:
        with self._lock:
            row = self._conn.execute(
                'SELECT COUNT(*) FROM request_queue WHERE status = ?',
                (status,),
            ).fetchone()
            return row[0]

    @staticmethod
    def _fingerprint(request: Request) -> str:
        digest = hashlib.sha256()  # SHA-256 hasher
        digest.update(request.method.upper().encode())
        digest.update(b'\0')
        digest.update(request.url.encode())
        digest.update(b'\0')
        digest.update(request.body or b'')  # fingerprint = sha256(method.upper(), url, body)
        return digest.hexdigest()  # hex fingerprint
