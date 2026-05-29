from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


ChatMessage = dict[str, str]
DEFAULT_CONVERSATION_USER_ID = "__dev__"
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ConversationUserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    conversations: Mapped[list[ConversationModel]] = relationship(back_populates="user")


class ConversationModel(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("user_id", "external_id", name="uq_conversations_user_external_id"),
        Index("idx_conversations_user_updated_at", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_message_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped[ConversationUserModel] = relationship(back_populates="conversations")
    messages: Mapped[list[MessageModel]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_conversation_id_id", "conversation_id", "id"),
        Index("idx_messages_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")


class DocumentModel(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("idx_documents_user_created_at", "user_id", "created_at"),
        Index("idx_documents_conversation_id", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class ToolCallLogModel(Base):
    __tablename__ = "tool_call_logs"
    __table_args__ = (
        Index("idx_tool_call_logs_conversation_created_at", "conversation_id", "created_at"),
        Index("idx_tool_call_logs_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AgentTraceModel(Base):
    __tablename__ = "agent_traces"
    __table_args__ = (
        Index("idx_agent_traces_conversation_created_at", "conversation_id", "created_at"),
        Index("idx_agent_traces_user_created_at", "user_id", "created_at"),
        Index("idx_agent_traces_trace_id", "trace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    trace_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    step: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    trace_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


@dataclass(frozen=True)
class StoredConversation:
    id: str
    user_id: str
    title: str
    last_message_summary: str
    message_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ConversationPage:
    conversations: list[StoredConversation]
    total: int
    limit: int
    offset: int
    has_more: bool


@dataclass(frozen=True)
class MessagePage:
    messages: list[ChatMessage]
    total: int
    limit: int
    offset: int
    has_more: bool


class ConversationStoreProtocol(Protocol):
    """Shared interface for conversation history stores."""

    max_rounds: int

    def get_messages(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> list[ChatMessage]:
        """Return recent user/assistant messages."""

    def get_message_page(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> MessagePage:
        """Return one paginated slice of messages."""

    def list_conversations(
        self,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> ConversationPage:
        """Return one paginated slice of conversations for a user."""

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
    conversation_meta: dict[tuple[str, str], StoredConversation] = field(default_factory=dict)
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
            return list(self.conversations.get(conversation_key(conversation_id, user_id), []))[-self.max_messages :]

    def get_message_page(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> MessagePage:
        with self._lock:
            messages = list(self.conversations.get(conversation_key(conversation_id, user_id), []))
        clean_limit, clean_offset = normalize_page(limit, offset)
        page_messages = messages[clean_offset : clean_offset + clean_limit]
        total = len(messages)
        return MessagePage(
            messages=page_messages,
            total=total,
            limit=clean_limit,
            offset=clean_offset,
            has_more=clean_offset + len(page_messages) < total,
        )

    def list_conversations(
        self,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> ConversationPage:
        clean_limit, clean_offset = normalize_page(limit, offset)
        with self._lock:
            items = [
                meta
                for key, meta in self.conversation_meta.items()
                if key[0] == str(user_id or DEFAULT_CONVERSATION_USER_ID)
            ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        page_items = items[clean_offset : clean_offset + clean_limit]
        total = len(items)
        return ConversationPage(
            conversations=page_items,
            total=total,
            limit=clean_limit,
            offset=clean_offset,
            has_more=clean_offset + len(page_items) < total,
        )

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
            trimmed_messages = messages[-self.max_messages :]
            self.conversations[key] = trimmed_messages
            self._upsert_meta(key, trimmed_messages)

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
            trimmed_messages = messages[-self.max_messages :]
            self.conversations[key] = trimmed_messages
            self._upsert_meta(key, trimmed_messages)

    def clear(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        with self._lock:
            key = conversation_key(conversation_id, user_id)
            self.conversations.pop(key, None)
            self.conversation_meta.pop(key, None)

    def _upsert_meta(self, key: tuple[str, str], messages: list[ChatMessage]) -> None:
        user_id, conversation_id = key
        now = utc_now().isoformat()
        existing = self.conversation_meta.get(key)
        title = existing.title if existing else title_from_messages(messages)
        summary = summarize_message(messages[-1]["content"]) if messages else ""
        self.conversation_meta[key] = StoredConversation(
            id=conversation_id,
            user_id=user_id,
            title=title,
            last_message_summary=summary,
            message_count=len(messages),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )


class SQLAlchemyConversationStore:
    """SQLAlchemy-backed conversation history store."""

    def __init__(
        self,
        db_path: str | Path = "data/conversations.db",
        max_rounds: int = 10,
        database_url: str | None = None,
    ) -> None:
        self.max_rounds = max_rounds
        self._lock = Lock()
        self.database_url = database_url or sqlite_url_from_path(db_path)
        if self.database_url.startswith("sqlite:///"):
            database_path = Path(str(make_url(self.database_url).database or ""))
            if str(database_path) != ":memory:":
                database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            self.database_url,
            future=True,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False} if self.database_url.startswith("sqlite") else {},
        )
        configure_sqlite_engine(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False, future=True)
        Base.metadata.create_all(self.engine)
        self._migrate_legacy_sqlite_messages()

    @property
    def max_messages(self) -> int:
        return self.max_rounds * 2

    def get_messages(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> list[ChatMessage]:
        """Return a copy of recent user/assistant messages."""

        clean_user_id = normalize_user_id(user_id)
        clean_conversation_id = str(conversation_id)
        with self._lock, self.session_factory() as session:
            conversation = self._get_conversation(session, clean_conversation_id, clean_user_id)
            if conversation is None:
                return []
            rows = session.execute(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation.id)
                .order_by(MessageModel.id.desc())
                .limit(self.max_messages)
            ).scalars().all()

        return [message_to_chat(row) for row in reversed(rows)]

    def get_message_page(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> MessagePage:
        clean_limit, clean_offset = normalize_page(limit, offset)
        clean_user_id = normalize_user_id(user_id)
        clean_conversation_id = str(conversation_id)
        with self._lock, self.session_factory() as session:
            conversation = self._get_conversation(session, clean_conversation_id, clean_user_id)
            if conversation is None:
                return MessagePage([], 0, clean_limit, clean_offset, False)
            total = session.scalar(
                select(func.count()).select_from(MessageModel).where(MessageModel.conversation_id == conversation.id)
            )
            rows = session.execute(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation.id)
                .order_by(MessageModel.id.asc())
                .limit(clean_limit)
                .offset(clean_offset)
            ).scalars().all()

        total_count = int(total or 0)
        messages = [message_to_chat(row) for row in rows]
        return MessagePage(
            messages=messages,
            total=total_count,
            limit=clean_limit,
            offset=clean_offset,
            has_more=clean_offset + len(messages) < total_count,
        )

    def list_conversations(
        self,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> ConversationPage:
        clean_limit, clean_offset = normalize_page(limit, offset)
        clean_user_id = normalize_user_id(user_id)
        with self._lock, self.session_factory() as session:
            total = session.scalar(
                select(func.count()).select_from(ConversationModel).where(ConversationModel.user_id == clean_user_id)
            )
            rows = session.execute(
                select(ConversationModel)
                .where(ConversationModel.user_id == clean_user_id)
                .order_by(ConversationModel.updated_at.desc(), ConversationModel.id.desc())
                .limit(clean_limit)
                .offset(clean_offset)
            ).scalars().all()

        total_count = int(total or 0)
        conversations = [conversation_to_stored(row) for row in rows]
        return ConversationPage(
            conversations=conversations,
            total=total_count,
            limit=clean_limit,
            offset=clean_offset,
            has_more=clean_offset + len(conversations) < total_count,
        )

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Append one message and trim the conversation to the latest rounds."""

        with self._lock, self.session_factory() as session:
            with session.begin():
                conversation = self._get_or_create_conversation(session, str(conversation_id), normalize_user_id(user_id))
                session.add(
                    MessageModel(
                        conversation_id=conversation.id,
                        user_id=conversation.user_id,
                        role=role,
                        content=content,
                    )
                )
                session.flush()
                self._refresh_conversation_summary(session, conversation, role, content)
                self._trim_conversation(session, conversation.id)

    def append_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_reply: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        """Append one user/assistant round and trim old context."""

        with self._lock, self.session_factory() as session:
            with session.begin():
                conversation = self._get_or_create_conversation(session, str(conversation_id), normalize_user_id(user_id))
                if not conversation.title or conversation.title == "New conversation":
                    conversation.title = summarize_message(user_message, max_chars=80) or "New conversation"
                session.add_all(
                    [
                        MessageModel(
                            conversation_id=conversation.id,
                            user_id=conversation.user_id,
                            role="user",
                            content=user_message,
                        ),
                        MessageModel(
                            conversation_id=conversation.id,
                            user_id=conversation.user_id,
                            role="assistant",
                            content=assistant_reply,
                        ),
                    ]
                )
                session.flush()
                self._refresh_conversation_summary(session, conversation, "assistant", assistant_reply)
                self._trim_conversation(session, conversation.id)

    def clear(
        self,
        conversation_id: str,
        user_id: str = DEFAULT_CONVERSATION_USER_ID,
    ) -> None:
        clean_user_id = normalize_user_id(user_id)
        clean_conversation_id = str(conversation_id)
        with self._lock, self.session_factory() as session:
            with session.begin():
                conversation = self._get_conversation(session, clean_conversation_id, clean_user_id)
                if conversation is not None:
                    session.delete(conversation)

    def _get_conversation(
        self,
        session: Session,
        conversation_id: str,
        user_id: str,
    ) -> ConversationModel | None:
        return session.execute(
            select(ConversationModel).where(
                ConversationModel.user_id == user_id,
                ConversationModel.external_id == conversation_id,
            )
        ).scalar_one_or_none()

    def _get_or_create_conversation(
        self,
        session: Session,
        conversation_id: str,
        user_id: str,
    ) -> ConversationModel:
        user = session.get(ConversationUserModel, user_id)
        if user is None:
            session.add(ConversationUserModel(id=user_id))
            session.flush()

        conversation = self._get_conversation(session, conversation_id, user_id)
        if conversation is not None:
            return conversation

        conversation = ConversationModel(
            user_id=user_id,
            external_id=conversation_id,
            title="New conversation",
            last_message_summary="",
            message_count=0,
        )
        session.add(conversation)
        session.flush()
        return conversation

    def _refresh_conversation_summary(
        self,
        session: Session,
        conversation: ConversationModel,
        role: str,
        content: str,
    ) -> None:
        if not conversation.title or conversation.title == "New conversation":
            if role == "user":
                conversation.title = summarize_message(content, max_chars=80) or "New conversation"
            else:
                first_user_message = session.execute(
                    select(MessageModel.content)
                    .where(MessageModel.conversation_id == conversation.id, MessageModel.role == "user")
                    .order_by(MessageModel.id.asc())
                    .limit(1)
                ).scalar_one_or_none()
                conversation.title = summarize_message(first_user_message or content, max_chars=80) or "New conversation"
        conversation.last_message_summary = summarize_message(content)
        conversation.message_count = int(conversation.message_count or 0) + 1
        conversation.updated_at = utc_now()

    def _trim_conversation(self, session: Session, conversation_pk: int) -> None:
        message_ids = session.execute(
            select(MessageModel.id)
            .where(MessageModel.conversation_id == conversation_pk)
            .order_by(MessageModel.id.desc())
            .offset(self.max_messages)
        ).scalars().all()
        if message_ids:
            session.query(MessageModel).filter(MessageModel.id.in_(message_ids)).delete(synchronize_session=False)

        total = session.scalar(
            select(func.count()).select_from(MessageModel).where(MessageModel.conversation_id == conversation_pk)
        )
        conversation = session.get(ConversationModel, conversation_pk)
        if conversation is not None:
            conversation.message_count = int(total or 0)

    def _migrate_legacy_sqlite_messages(self) -> None:
        if self.engine.dialect.name != "sqlite":
            return
        inspector = inspect(self.engine)
        if "conversation_messages" not in inspector.get_table_names():
            return

        with self._lock, self.session_factory() as session:
            with session.begin():
                existing_messages = session.scalar(select(func.count()).select_from(MessageModel))
                if existing_messages:
                    return
                rows = session.execute(
                    text(
                        """
                        SELECT user_id, conversation_id, role, content, created_at
                        FROM conversation_messages
                        ORDER BY id ASC
                        """
                    )
                ).mappings().all()
                if not rows:
                    return
                for row in rows:
                    user_id = normalize_user_id(str(row["user_id"]))
                    conversation = self._get_or_create_conversation(session, str(row["conversation_id"]), user_id)
                    session.add(
                        MessageModel(
                            conversation_id=conversation.id,
                            user_id=user_id,
                            role=str(row["role"]),
                            content=str(row["content"]),
                            created_at=parse_datetime(row["created_at"]),
                        )
                    )
                    self._refresh_conversation_summary(session, conversation, str(row["role"]), str(row["content"]))


def conversation_key(conversation_id: str, user_id: str = DEFAULT_CONVERSATION_USER_ID) -> tuple[str, str]:
    return (normalize_user_id(user_id), str(conversation_id))


def create_conversation_store(
    store_type: str = "memory",
    db_path: str | Path = "data/conversations.db",
    max_rounds: int = 10,
    database_url: str | None = None,
) -> ConversationStoreProtocol:
    """Create a conversation store based on configuration."""

    normalized_store_type = store_type.strip().lower()
    if normalized_store_type in {"sqlite", "sqlalchemy", "postgresql", "postgres", "mysql"}:
        return SQLAlchemyConversationStore(db_path=db_path, max_rounds=max_rounds, database_url=database_url)
    return ConversationStore(max_rounds=max_rounds)


def configure_sqlite_engine(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=3000")
        cursor.execute("PRAGMA foreign_keys=ON")
        if str(engine.url.database or "") != ":memory:":
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def sqlite_url_from_path(db_path: str | Path) -> str:
    if str(db_path) == ":memory:":
        return "sqlite:///:memory:"
    return f"sqlite:///{Path(db_path).as_posix()}"


def normalize_user_id(user_id: str = DEFAULT_CONVERSATION_USER_ID) -> str:
    return str(user_id or DEFAULT_CONVERSATION_USER_ID)


def normalize_page(limit: int = DEFAULT_PAGE_LIMIT, offset: int = 0) -> tuple[int, int]:
    clean_limit = max(1, min(int(limit or DEFAULT_PAGE_LIMIT), MAX_PAGE_LIMIT))
    clean_offset = max(0, int(offset or 0))
    return clean_limit, clean_offset


def summarize_message(content: str | None, max_chars: int = 120) -> str:
    text_value = " ".join(str(content or "").split())
    if len(text_value) <= max_chars:
        return text_value
    return text_value[: max_chars - 3].rstrip() + "..."


def title_from_messages(messages: list[ChatMessage]) -> str:
    for message in messages:
        if message.get("role") == "user":
            return summarize_message(message.get("content"), max_chars=80) or "New conversation"
    return "New conversation"


def message_to_chat(row: MessageModel) -> ChatMessage:
    return {"role": str(row.role), "content": str(row.content)}


def conversation_to_stored(row: ConversationModel) -> StoredConversation:
    return StoredConversation(
        id=str(row.external_id),
        user_id=str(row.user_id),
        title=row.title or "New conversation",
        last_message_summary=row.last_message_summary or "",
        message_count=int(row.message_count or 0),
        created_at=format_datetime(row.created_at),
        updated_at=format_datetime(row.updated_at),
    )


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value is None:
        return utc_now()
    text_value = str(value)
    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(text_value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return utc_now()


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return utc_now().isoformat()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.isoformat()
