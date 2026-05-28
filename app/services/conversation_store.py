from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Protocol


ChatMessage = dict[str, str]
DEFAULT_CONVERSATION_USER_ID = "__dev__"


class ConversationStoreProtocol(Protocol):
    """Shared interface for conversation history stores."""

    max_rounds: int

    def get_messages(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> list[ChatMessage]:
        """Return recent user/assistant messages."""

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Append one message."""

    def append_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_reply: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Append one user/assistant round."""

    def clear(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Clear one conversation."""


@dataclass
class ConversationStore:
    """In-memory conversation history store."""

    max_rounds: int = 10
    conversations: dict[tuple[str, str], list[ChatMessage]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    @property
    def max_messages(self) -> int:
        return self.max_rounds * 2

    def get_messages(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> list[ChatMessage]:
        """Return a copy of recent user/assistant messages."""

        with self._lock:
            return list(self.conversations.get(conversation_key(conversation_id, user_id), []))

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Append one message and trim the conversation to the latest rounds."""

        with self._lock:
            key = conversation_key(conversation_id, user_id)
            messages = self.conversations.setdefault(key, [])
            messages.append({"role": role, "content": content})
            self.conversations[key] = messages[-self.max_messages :]

    def append_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_reply: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Append one user/assistant round and trim old context."""

        with self._lock:
            key = conversation_key(conversation_id, user_id)
            messages = self.conversations.setdefault(key, [])
            messages.extend(
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_reply},
                ]
            )
            self.conversations[key] = messages[-self.max_messages :]

    def clear(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        with self._lock:
            self.conversations.pop(conversation_key(conversation_id, user_id), None)


class SQLiteConversationStore:
    """SQLite-backed conversation history store."""

    def __init__(self, db_path: str | Path = "data/conversations.db", max_rounds: int = 10) -> None:
        self.db_path = Path(db_path)
        self._is_memory_database = str(db_path) == ":memory:"
        self.max_rounds = max_rounds
        self._lock = Lock()
        if not self._is_memory_database:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._configure_connection()
        self._initialize_database()

    @property
    def max_messages(self) -> int:
        return self.max_rounds * 2

    def get_messages(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> list[ChatMessage]:
        """Return a copy of recent user/assistant messages."""

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT role, content
                FROM (
                    SELECT id, role, content
                    FROM conversation_messages
                    WHERE user_id = ? AND conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (user_id, conversation_id, self.max_messages),
            ).fetchall()

        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Append one message and trim the conversation to the latest rounds."""

        with self._lock, self._connection:
            self._insert_message(self._connection, conversation_id, role, content, user_id)
            self._trim_conversation(self._connection, conversation_id, user_id)

    def append_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_reply: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Append one user/assistant round and trim old context."""

        with self._lock, self._connection:
            self._insert_message(self._connection, conversation_id, "user", user_message, user_id)
            self._insert_message(self._connection, conversation_id, "assistant", assistant_reply, user_id)
            self._trim_conversation(self._connection, conversation_id, user_id)

    def clear(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM conversation_messages WHERE user_id = ? AND conversation_id = ?",
                (user_id, conversation_id),
            )

    def _configure_connection(self) -> None:
        if not self._is_memory_database:
            self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=3000")

    def _initialize_database(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT '__dev__',
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_user_id_column()
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_user_conversation_id
                ON conversation_messages (user_id, conversation_id, id)
                """
            )

    def _ensure_user_id_column(self) -> None:
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(conversation_messages)").fetchall()
        }
        if "user_id" in columns:
            return
        self._connection.execute(
            "ALTER TABLE conversation_messages ADD COLUMN user_id TEXT NOT NULL DEFAULT '__dev__'"
        )

    def _insert_message(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        connection.execute(
            """
            INSERT INTO conversation_messages (user_id, conversation_id, role, content)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, conversation_id, role, content),
        )

    def _trim_conversation(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        connection.execute(
            """
            DELETE FROM conversation_messages
            WHERE user_id = ?
              AND conversation_id = ?
              AND id NOT IN (
                  SELECT id
                  FROM conversation_messages
                  WHERE user_id = ?
                    AND conversation_id = ?
                  ORDER BY id DESC
                  LIMIT ?
              )
            """,
            (user_id, conversation_id, user_id, conversation_id, self.max_messages),
        )


def conversation_key(conversation_id: str, user_id: str = DEFAULT_CONVERSATION_USER_ID) -> tuple[str, str]:
    return (str(user_id or DEFAULT_CONVERSATION_USER_ID), str(conversation_id))


def create_conversation_store(
    store_type: str = "memory",
    db_path: str | Path = "data/conversations.db",
    max_rounds: int = 10,
) -> ConversationStoreProtocol:
    """Create a conversation store based on configuration."""

    normalized_store_type = store_type.strip().lower()
    if normalized_store_type == "sqlite":
        return SQLiteConversationStore(db_path=db_path, max_rounds=max_rounds)
    return ConversationStore(max_rounds=max_rounds)
