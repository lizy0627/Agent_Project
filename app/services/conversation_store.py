from dataclasses import dataclass, field
from threading import Lock


ChatMessage = dict[str, str]


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
