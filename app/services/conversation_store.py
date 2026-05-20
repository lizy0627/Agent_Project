from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Protocol


ChatMessage = dict[str, str]


class ConversationStoreProtocol(Protocol):
    """Shared interface for conversation history stores."""

    max_rounds: int

    def get_messages(self, conversation_id: str) -> list[ChatMessage]:
        """Return recent user/assistant messages."""

    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        """Append one message."""

    def append_exchange(self, conversation_id: str, user_message: str, assistant_reply: str) -> None:
        """Append one user/assistant round."""

    def clear(self, conversation_id: str) -> None:
        """Clear one conversation."""


@dataclass
class ConversationStore:
    """In-memory conversation history store."""

    max_rounds: int = 10
    conversations: dict[str, list[ChatMessage]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    @property
    def max_messages(self) -> int:
        return self.max_rounds * 2

    def get_messages(self, conversation_id: str) -> list[ChatMessage]:
        """Return a copy of recent user/assistant messages."""

        with self._lock:
            return list(self.conversations.get(conversation_id, []))

    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        """Append one message and trim the conversation to the latest rounds."""

        with self._lock:
            messages = self.conversations.setdefault(conversation_id, [])
            messages.append({"role": role, "content": content})
            self.conversations[conversation_id] = messages[-self.max_messages :]

    def append_exchange(self, conversation_id: str, user_message: str, assistant_reply: str) -> None:
        """Append one user/assistant round and trim old context."""

        with self._lock:
            messages = self.conversations.setdefault(conversation_id, [])
            messages.extend(
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_reply},
                ]
            )
            self.conversations[conversation_id] = messages[-self.max_messages :]

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self.conversations.pop(conversation_id, None)


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

    def get_messages(self, conversation_id: str) -> list[ChatMessage]:
        """Return a copy of recent user/assistant messages."""

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT role, content
                FROM (
                    SELECT id, role, content
                    FROM conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (conversation_id, self.max_messages),
            ).fetchall()

        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        """Append one message and trim the conversation to the latest rounds."""

        with self._lock, self._connection:
            self._insert_message(self._connection, conversation_id, role, content)
            self._trim_conversation(self._connection, conversation_id)

    def append_exchange(self, conversation_id: str, user_message: str, assistant_reply: str) -> None:
        """Append one user/assistant round and trim old context."""

        with self._lock, self._connection:
            self._insert_message(self._connection, conversation_id, "user", user_message)
            self._insert_message(self._connection, conversation_id, "assistant", assistant_reply)
            self._trim_conversation(self._connection, conversation_id)

    def clear(self, conversation_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?",
                (conversation_id,),
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
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id_id
                ON conversation_messages (conversation_id, id)
                """
            )

    def _insert_message(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO conversation_messages (conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (conversation_id, role, content),
        )

    def _trim_conversation(self, connection: sqlite3.Connection, conversation_id: str) -> None:
        connection.execute(
            """
            DELETE FROM conversation_messages
            WHERE conversation_id = ?
              AND id NOT IN (
                  SELECT id
                  FROM conversation_messages
                  WHERE conversation_id = ?
                  ORDER BY id DESC
                  LIMIT ?
              )
            """,
            (conversation_id, conversation_id, self.max_messages),
        )


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
