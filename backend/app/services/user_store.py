from dataclasses import dataclass
from pathlib import Path
import sqlite3
from threading import Lock

import bcrypt


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: str
    created_at: str


class UserAlreadyExistsError(ValueError):
    """Raised when a username is already registered."""


class UserStore:
    """SQLite-backed local user store."""

    def __init__(self, db_path: str | Path = "data/auth.db") -> None:
        self.db_path = Path(db_path)
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._configure_connection()
        self._initialize_database()

    def create_user(self, username: str, password: str) -> User:
        clean_username = normalize_username(username)
        password_hash = hash_password(password)
        try:
            with self._lock, self._connection:
                cursor = self._connection.execute(
                    """
                    INSERT INTO users (username, password_hash)
                    VALUES (?, ?)
                    """,
                    (clean_username, password_hash),
                )
                user_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExistsError(clean_username) from exc

        user = self.get_user_by_id(user_id)
        if user is None:
            raise LookupError("Created user cannot be loaded.")
        return user

    def get_user_by_id(self, user_id: int) -> User | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, username, password_hash, created_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

        return self._row_to_user(row) if row else None

    def get_user_by_username(self, username: str) -> User | None:
        clean_username = normalize_username(username)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, username, password_hash, created_at
                FROM users
                WHERE username = ?
                """,
                (clean_username,),
            ).fetchone()

        return self._row_to_user(row) if row else None

    def verify_user(self, username: str, password: str) -> User | None:
        user = self.get_user_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            return None
        return user

    def _configure_connection(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=3000")

    def _initialize_database(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_users_username
                ON users (username)
                """
            )

    def _row_to_user(self, row: sqlite3.Row) -> User:
        return User(
            id=int(row["id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            created_at=str(row["created_at"]),
        )


def normalize_username(username: str) -> str:
    return " ".join(str(username or "").strip().split())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
