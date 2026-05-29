from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from threading import Lock
from uuid import uuid4

from backend.app.core.logger import get_logger


logger = get_logger(__name__)
DEFAULT_DOCUMENT_USER_ID = "__dev__"

TEXT_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
PDF_CONTENT_TYPES = {"application/pdf"}
PDF_EXTENSIONS = {".pdf"}
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
MAX_REFERENCE_CHARS = 800


@dataclass(frozen=True)
class StoredDocument:
    id: str
    filename: str
    content_type: str
    size_bytes: int
    chunk_count: int
    created_at: str


@dataclass(frozen=True)
class DocumentChunk:
    document_id: str
    chunk_index: int
    content: str
    created_at: str
    score: float = 0.0


class DocumentValidationError(ValueError):
    """Raised when an uploaded document is not safe or supported."""


class DocumentNotFoundError(LookupError):
    """Raised when a document id does not exist."""


class DocumentStore:
    """SQLite-backed document metadata, chunk storage, and keyword retrieval."""

    def __init__(self, db_path: str | Path = "data/documents.db") -> None:
        self.db_path = Path(db_path)
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._configure_connection()
        self._initialize_database()

    def list_documents(self, user_id: str = DEFAULT_DOCUMENT_USER_ID) -> list[StoredDocument]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, filename, content_type, size_bytes, chunk_count, created_at
                FROM documents
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()

        return [self._row_to_document(row) for row in rows]

    def get_document(self, document_id: str, user_id: str = DEFAULT_DOCUMENT_USER_ID) -> StoredDocument:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, filename, content_type, size_bytes, chunk_count, created_at
                FROM documents
                WHERE id = ? AND user_id = ?
                """,
                (document_id, user_id),
            ).fetchone()

        if row is None:
            raise DocumentNotFoundError(document_id)
        return self._row_to_document(row)

    def create_document(
        self,
        filename: str,
        content_type: str,
        size_bytes: int,
        text: str,
        user_id: str = DEFAULT_DOCUMENT_USER_ID,
    ) -> StoredDocument:
        chunks = split_text_into_chunks(text)
        if not chunks:
            raise DocumentValidationError("文档没有可解析的文本内容。")

        document_id = str(uuid4())
        clean_filename = sanitize_filename(filename)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO documents (id, user_id, filename, content_type, size_bytes, chunk_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (document_id, user_id, clean_filename, content_type, size_bytes, len(chunks)),
            )
            self._connection.executemany(
                """
                INSERT INTO document_chunks (document_id, chunk_index, content)
                VALUES (?, ?, ?)
                """,
                [(document_id, index, chunk) for index, chunk in enumerate(chunks)],
            )

        logger.info(
            "Document indexed: id=%s filename=%s size_bytes=%s chunks=%s",
            document_id,
            clean_filename,
            size_bytes,
            len(chunks),
        )
        return self.get_document(document_id, user_id=user_id)

    def delete_document(self, document_id: str, user_id: str = DEFAULT_DOCUMENT_USER_ID) -> None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM documents WHERE id = ? AND user_id = ?",
                (document_id, user_id),
            )

        if cursor.rowcount == 0:
            raise DocumentNotFoundError(document_id)
        logger.info("Document deleted: id=%s", document_id)

    def search_chunks(
        self,
        document_id: str,
        question: str,
        top_k: int = 5,
        user_id: str = DEFAULT_DOCUMENT_USER_ID,
    ) -> list[DocumentChunk]:
        self.get_document(document_id, user_id=user_id)
        terms = extract_search_terms(question)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT document_id, chunk_index, content, created_at
                FROM document_chunks
                WHERE document_id = ?
                ORDER BY chunk_index ASC
                """,
                (document_id,),
            ).fetchall()

        chunks = [self._row_to_chunk(row) for row in rows]
        if not chunks:
            return []

        scored_chunks = [
            DocumentChunk(
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                created_at=chunk.created_at,
                score=score_chunk(chunk.content, terms),
            )
            for chunk in chunks
        ]
        matched_chunks = [chunk for chunk in scored_chunks if chunk.score > 0]
        if matched_chunks:
            return sorted(matched_chunks, key=lambda item: (-item.score, item.chunk_index))[:top_k]

        # With no keyword hit, use the opening chunks so the model can still answer broad questions.
        return scored_chunks[:top_k]

    def _configure_connection(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=3000")
        self._connection.execute("PRAGMA foreign_keys=ON")

    def _initialize_database(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT '__dev__',
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_document_user_id_column()
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_user_created_at
                ON documents (user_id, created_at DESC)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id_index
                ON document_chunks (document_id, chunk_index)
                """
            )

    def _ensure_document_user_id_column(self) -> None:
        columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(documents)").fetchall()}
        if "user_id" in columns:
            return
        self._connection.execute("ALTER TABLE documents ADD COLUMN user_id TEXT NOT NULL DEFAULT '__dev__'")

    def _row_to_document(self, row: sqlite3.Row) -> StoredDocument:
        return StoredDocument(
            id=row["id"],
            filename=row["filename"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            chunk_count=row["chunk_count"],
            created_at=row["created_at"],
        )

    def _row_to_chunk(self, row: sqlite3.Row) -> DocumentChunk:
        return DocumentChunk(
            document_id=row["document_id"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            created_at=row["created_at"],
        )


def parse_upload_text(filename: str, content_type: str | None, data: bytes) -> tuple[str, str]:
    """Parse an uploaded txt/md/pdf file into plain text."""

    suffix = Path(filename or "").suffix.lower()
    normalized_content_type = (content_type or "application/octet-stream").split(";")[0].strip().lower()

    if suffix in TEXT_EXTENSIONS:
        return decode_text_file(data), normalized_content_type

    if suffix in PDF_EXTENSIONS or normalized_content_type in PDF_CONTENT_TYPES:
        return extract_pdf_text(data), "application/pdf"

    if normalized_content_type in TEXT_CONTENT_TYPES:
        return decode_text_file(data), normalized_content_type

    raise DocumentValidationError("仅支持 txt、md、pdf 文件。")


def decode_text_file(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentValidationError("文本编码无法识别，请上传 UTF-8 或 GB18030 文本。")


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentValidationError("PDF 解析依赖未安装，请先安装 pypdf，或上传 txt/md 文件。") from exc

    from io import BytesIO

    try:
        reader = PdfReader(BytesIO(data))
        page_text = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise DocumentValidationError("PDF 文件解析失败，请检查文件是否损坏。") from exc

    return "\n\n".join(page_text)


def sanitize_filename(filename: str) -> str:
    clean_name = Path(filename or "document").name.strip()
    if not clean_name:
        return "document"
    return clean_name[:180]


def split_text_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    normalized_text = re.sub(r"\s+", " ", text).strip()
    if not normalized_text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized_text):
        end = min(len(normalized_text), start + chunk_size)
        chunks.append(normalized_text[start:end].strip())
        if end >= len(normalized_text):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def extract_search_terms(question: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", question.lower())
    return [word for word in words if len(word) > 1 or "\u4e00" <= word <= "\u9fff"]


def score_chunk(content: str, terms: list[str]) -> float:
    if not terms:
        return 0.0

    lowered_content = content.lower()
    score = 0.0
    for term in terms:
        score += lowered_content.count(term)
    return score


def build_document_prompt(question: str, document: StoredDocument, chunks: list[DocumentChunk]) -> str:
    """Build a grounded prompt with explicit document context boundaries."""

    references = []
    for chunk in chunks:
        content = chunk.content[:MAX_REFERENCE_CHARS]
        references.append(f"[chunk {chunk.chunk_index}]\n{content}")

    context = "\n\n".join(references) if references else "未检索到相关片段。"
    return (
        "请基于下方文档片段回答用户问题。"
        "如果片段中没有答案，请明确说明文档中没有足够信息，不要编造。\n\n"
        f"文档：{document.filename}\n"
        f"用户问题：{question}\n\n"
        f"文档片段：\n{context}"
    )
