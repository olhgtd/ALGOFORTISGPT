"""Serialize a dashboard connection, including reads during shared transactions."""
import sqlite3
from threading import RLock


class SerializedCursor(sqlite3.Cursor):
    def execute(self, *args, **kwargs):
        with self.connection.access_lock:
            return super().execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        with self.connection.access_lock:
            return super().executemany(*args, **kwargs)

    def fetchone(self):
        with self.connection.access_lock:
            return super().fetchone()

    def fetchall(self):
        with self.connection.access_lock:
            return super().fetchall()

    def __next__(self):
        with self.connection.access_lock:
            return super().__next__()

    def close(self):
        with self.connection.access_lock:
            return super().close()


class SerializedConnection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.access_lock = RLock()

    def cursor(self, factory=SerializedCursor):
        with self.access_lock:
            return super().cursor(factory)

    def execute(self, *args, **kwargs):
        with self.access_lock:
            return self.cursor().execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        with self.access_lock:
            return self.cursor().executemany(*args, **kwargs)

    def commit(self):
        with self.access_lock:
            return super().commit()

    def rollback(self):
        with self.access_lock:
            return super().rollback()

    def close(self):
        with self.access_lock:
            return super().close()
