from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from threading import RLock

from ..model import CrawlTask, Request
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
            self._conn.execute('DROP TABLE IF EXISTS crawl_tasks')
        self._init()
        self._recover()

    def open(self) -> None:
        pass

    def enqueue(self, request: Request) -> bool:
        payload = self.codec.encode(request)
        fingerprint = None if request.dont_filter else self._fingerprint(request)  # None does not violate UNIQUE
        with self._lock:  # lock the connection
            cursor = self._conn.execute(
                '''
                INSERT OR IGNORE INTO crawl_tasks
                    (fingerprint, payload, priority, status, attempt)
                VALUES (?, ?, ?, ?, 0)
                ''',
                (fingerprint, payload, request.priority, PENDING),
            )
            return cursor.rowcount == 1

    def dequeue(self) -> CrawlTask | None:
        with self._lock:
            self._conn.execute('BEGIN IMMEDIATE')  # start a transaction and acquire a write lock
            try:
                row = self._conn.execute(
                    '''
                    SELECT id, payload, attempt
                    FROM crawl_tasks
                    WHERE status = ?
                    ORDER BY priority DESC, id ASC
                    LIMIT 1
                    ''',
                    (PENDING,),
                ).fetchone()
                if row is None:
                    self._conn.commit()  # persist changes and release the lock
                    return None
                self._conn.execute(
                    '''
                    UPDATE crawl_tasks
                    SET status = ?, error = NULL
                    WHERE id = ?
                    ''',
                    (LEASED, row[0]),
                )
                self._conn.commit()
                task = CrawlTask(
                    id=row[0],
                    request=self.codec.decode(row[1]),
                    attempt=row[2],
                )
                return task
            except Exception:
                self._conn.rollback()  # roll back the transaction on error
                raise  # re-raise the original exception

    def mark_done(self, task: CrawlTask) -> None:
        self._transition(task, DONE, None)

    def mark_failed(self, task: CrawlTask, error: Exception) -> None:
        self._transition(task, FAILED, str(error))

    def requeue(self, task: CrawlTask, error: Exception) -> None:
        with self._lock:
            cursor = self._conn.execute(
                '''
                UPDATE crawl_tasks
                SET status = ?, attempt = attempt + 1, error = ?
                WHERE id = ? AND status = ?
                ''',
                (PENDING, str(error), task.id, LEASED),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f'task is not leased: {task.id}')

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
            CREATE TABLE IF NOT EXISTS crawl_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE,
                payload TEXT NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                error TEXT
            )
            '''
        )  # non-null fingerprint must be unique
        self._conn.execute(
            '''
            CREATE INDEX IF NOT EXISTS idx_crawl_tasks_status_priority
            ON crawl_tasks(status, priority DESC, id ASC)
            '''
        )

    def _recover(self) -> None:
        self._conn.execute(
            'UPDATE crawl_tasks SET status = ? WHERE status = ?',
            (PENDING, LEASED),
        )

    def _transition(self, task: CrawlTask, status: str, error: str | None) -> None:
        with self._lock:
            cursor = self._conn.execute(
                '''
                UPDATE crawl_tasks
                SET status = ?, error = ?
                WHERE id = ? AND status = ?
                ''',
                (status, error, task.id, LEASED),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f'task is not leased: {task.id}')

    def _count(self, status: str) -> int:
        with self._lock:
            row = self._conn.execute(
                'SELECT COUNT(*) FROM crawl_tasks WHERE status = ?',
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
