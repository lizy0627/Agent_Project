from threading import Lock

from fastapi import APIRouter, Depends, File, Path, UploadFile
from fastapi.responses import JSONResponse

from app.api.auth import CurrentUser, get_current_user
from app.api.chat import get_agent, normalize_requested_model
from app.core.config import Settings, get_settings
from app.core.exceptions import ErrorCode, InvalidArgumentsError, NotFoundError, UnknownAgentError, error_response
from app.core.logger import get_logger
from app.schemas.documents import (
    DocumentAskRequest,
    DocumentAskResponse,
    DocumentChunkReference,
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentSummary,
    DocumentUploadResponse,
)
from app.services.dashscope_agent import DashScopeAgent
from app.services.document_store import (
    DocumentNotFoundError,
    DocumentStore,
    DocumentValidationError,
    StoredDocument,
    build_document_prompt,
    parse_upload_text,
)


router = APIRouter(prefix="/documents", tags=["documents"])
logger = get_logger(__name__)
store_lock = Lock()
cached_document_store: DocumentStore | None = None
cached_document_store_signature: str | None = None


def get_document_store(settings: Settings = Depends(get_settings)) -> DocumentStore:
    """Return the configured document store singleton."""

    global cached_document_store, cached_document_store_signature

    signature = str(settings.document_db_path)
    with store_lock:
        if cached_document_store is None or cached_document_store_signature != signature:
            cached_document_store = DocumentStore(settings.document_db_path)
            cached_document_store_signature = signature
            logger.info("Document store initialized: db_path=%s", settings.document_db_path)

        return cached_document_store


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(get_document_store),
) -> DocumentUploadResponse | JSONResponse:
    """Upload, parse, chunk, and index one txt/md/pdf document."""

    try:
        filename = validate_upload_filename(file.filename)
        data = await file.read(settings.document_upload_max_bytes + 1)
        if len(data) > settings.document_upload_max_bytes:
            logger.info("Document upload rejected by size: filename=%s", filename)
            return invalid_document_response("文件过大，请上传不超过 5MB 的文档。")
        if not data:
            return invalid_document_response("上传文件为空。")

        text, content_type = parse_upload_text(filename, file.content_type, data)
        document = store.create_document(
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            text=text,
            user_id=current_user.user_id,
        )
        return DocumentUploadResponse(document=document_summary(document))
    except DocumentValidationError as exc:
        logger.info("Document upload validation failed: %s", exc)
        return invalid_document_response(str(exc))
    except Exception:
        logger.exception("Unhandled document upload error")
        return unknown_document_response()
    finally:
        await file.close()


@router.get("", response_model=DocumentListResponse)
@router.get("/", response_model=DocumentListResponse, include_in_schema=False)
def list_documents(
    current_user: CurrentUser = Depends(get_current_user),
    store: DocumentStore = Depends(get_document_store),
) -> DocumentListResponse | JSONResponse:
    """Return uploaded documents."""

    try:
        return DocumentListResponse(
            documents=[document_summary(document) for document in store.list_documents(user_id=current_user.user_id)],
        )
    except Exception:
        logger.exception("Unhandled document list error")
        return unknown_document_response()


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: str = Path(..., min_length=1, max_length=100),
    current_user: CurrentUser = Depends(get_current_user),
    store: DocumentStore = Depends(get_document_store),
) -> DocumentDeleteResponse | JSONResponse:
    """Delete one document and its chunks."""

    try:
        clean_document_id = document_id.strip()
        if not clean_document_id:
            return invalid_document_response("document_id 不能为空。")
        store.delete_document(clean_document_id, user_id=current_user.user_id)
        return DocumentDeleteResponse(document_id=clean_document_id, message="文档已删除")
    except DocumentNotFoundError:
        return document_not_found_response()
    except Exception:
        logger.exception("Unhandled document delete error")
        return unknown_document_response()


@router.post("/{document_id}/ask", response_model=DocumentAskResponse)
def ask_document(
    request: DocumentAskRequest,
    document_id: str = Path(..., min_length=1, max_length=100),
    current_user: CurrentUser = Depends(get_current_user),
    store: DocumentStore = Depends(get_document_store),
    agent: DashScopeAgent = Depends(get_agent),
) -> DocumentAskResponse | JSONResponse:
    """Retrieve relevant chunks and ask the existing DashScopeAgent to answer."""

    try:
        clean_document_id = document_id.strip()
        if not clean_document_id:
            return invalid_document_response("document_id 不能为空。")

        document = store.get_document(clean_document_id, user_id=current_user.user_id)
        chunks = store.search_chunks(
            clean_document_id,
            request.question,
            top_k=request.top_k,
            user_id=current_user.user_id,
        )
        prompt = build_document_prompt(request.question, document, chunks)
        requested_model = normalize_requested_model(request.model)
        reply = agent.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个严谨的文档问答助手，只根据用户提供的文档片段作答。",
                },
                {"role": "user", "content": prompt},
            ],
            model=requested_model,
        )
        logger.info(
            "Document question answered: document_id=%s chunks=%s model=%s",
            clean_document_id,
            len(chunks),
            requested_model or agent.model,
        )
        return DocumentAskResponse(
            document_id=clean_document_id,
            answer=reply.content,
            model=requested_model or agent.model,
            chunks=[
                DocumentChunkReference(
                    chunk_index=chunk.chunk_index,
                    content=chunk.content[:500],
                    score=chunk.score,
                )
                for chunk in chunks
            ],
        )
    except DocumentNotFoundError:
        return document_not_found_response()
    except DocumentValidationError as exc:
        logger.info("Document ask validation failed: %s", exc)
        return invalid_document_response(str(exc))
    except Exception:
        logger.exception("Unhandled document ask error")
        return unknown_document_response()


def validate_upload_filename(filename: str | None) -> str:
    clean_filename = (filename or "").strip()
    if not clean_filename:
        raise DocumentValidationError("文件名不能为空。")
    if "/" in clean_filename or "\\" in clean_filename:
        raise DocumentValidationError("文件名不能包含路径。")
    return clean_filename


def document_summary(document: StoredDocument) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
    )


def invalid_document_response(message: str) -> JSONResponse:
    return error_response(InvalidArgumentsError(message), message=message)


def document_not_found_response() -> JSONResponse:
    return error_response(
        NotFoundError(message="文档不存在或已被删除。", code=ErrorCode.DOCUMENT_NOT_FOUND),
    )


def unknown_document_response() -> JSONResponse:
    return error_response(UnknownAgentError(), message="文档服务暂时异常，请稍后重试。")
