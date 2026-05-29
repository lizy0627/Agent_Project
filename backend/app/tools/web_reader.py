from html.parser import HTMLParser
import re
from threading import Lock
from time import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.app.core.logger import get_logger
from backend.app.tools.base import BaseTool

try:
    import trafilatura
except ImportError:  # pragma: no cover - optional runtime dependency fallback
    trafilatura = None


logger = get_logger(__name__)
WEB_READER_CACHE_TTL_SECONDS = 10 * 60
WEB_READER_CACHE_MAX_SIZE = 100
_WEB_READER_CACHE: dict[str, tuple[float, dict]] = {}
_WEB_READER_CACHE_LOCK = Lock()


class _ReadableHTMLParser(HTMLParser):
    """Extract readable text from common HTML pages."""

    ignored_tags = {
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "button",
    }
    ignored_attr_keywords = (
        "ads",
        "advert",
        "advertisement",
        "banner",
        "comment",
        "comments",
        "discussion",
        "reply",
        "footer",
        "header",
        "nav",
        "menu",
        "sidebar",
        "share",
        "social",
        "cookie",
        "subscribe",
        "newsletter",
        "popup",
        "modal",
        "广告",
        "评论",
        "评论区",
    )
    block_tags = {
        "title",
        "h1",
        "h2",
        "h3",
        "p",
        "article",
        "main",
        "section",
        "li",
        "blockquote",
    }

    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self._ignored_tag_stack: list[str] = []
        self._tag_stack: list[str] = []
        self._title_chunks: list[str] = []
        self._blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        if self._should_ignore(tag, attrs):
            self._ignored_depth += 1
            self._ignored_tag_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._ignored_tag_stack and tag == self._ignored_tag_stack[-1]:
            self._ignored_depth -= 1
            self._ignored_tag_stack.pop()
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return

        text = " ".join(data.split())
        if not text or self._looks_like_noise(text):
            return

        current_tag = self._tag_stack[-1] if self._tag_stack else ""
        if current_tag == "title":
            self._title_chunks.append(text)
        elif current_tag in self.block_tags or any(tag in self.block_tags for tag in self._tag_stack):
            self._blocks.append(text)
        elif len(text) >= 40:
            self._blocks.append(text)

    def text(self) -> str:
        chunks = []
        title = self.title()
        if title:
            chunks.append(title)
        chunks.extend(self._blocks)
        return "\n\n".join(self._dedupe(chunks))

    def title(self) -> str:
        return " ".join(self._title_chunks).strip()

    def _should_ignore(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in self.ignored_tags:
            return True

        attr_text = " ".join(
            str(value or "") for name, value in attrs if name in {"id", "class", "role", "aria-label"}
        )
        attr_text = attr_text.lower()
        attr_tokens = set(re.split(r"[^a-z0-9\u4e00-\u9fff]+", attr_text))
        if attr_tokens.intersection(self.ignored_attr_keywords):
            return True
        return any(keyword in attr_text for keyword in ("advertisement", "广告", "评论区"))

    def _looks_like_noise(self, text: str) -> bool:
        lowered = text.lower()
        noise_keywords = (
            "广告",
            "评论",
            "发表评论",
            "相关阅读",
            "相关推荐",
            "点击加载更多",
            "advertisement",
            "sponsored",
            "comments",
            "leave a comment",
            "related articles",
        )
        return any(keyword in lowered for keyword in noise_keywords)

    def _dedupe(self, chunks: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for chunk in chunks:
            normalized = " ".join(chunk.split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped


class WebReaderTool(BaseTool):
    """Fetch a web page and return readable text."""

    name = "web_reader"
    description = "Read a web page and extract readable text."
    args_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "HTTP or HTTPS URL to read.",
            },
        },
        "required": ["url"],
    }
    default_timeout_seconds = 5.0
    max_content_chars = 3000

    def __init__(self, timeout_seconds: float | int | None = None) -> None:
        self.timeout_seconds = self._normalize_timeout(timeout_seconds, self.default_timeout_seconds)

    def run(self, url: str) -> dict[str, Any]:
        original_url = url.strip()
        if not original_url:
            raise ValueError("URL is empty.")
        if not original_url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://.")

        cache_key = self._normalize_url(original_url)
        cached_result = self._get_cached_result(cache_key)
        if cached_result is not None:
            logger.info("Web reader cache hit: url=%s", cache_key)
            return {**cached_result, "cached": True}

        logger.info("Web reader cache miss: url=%s", cache_key)

        try:
            response = httpx.get(
                original_url,
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 DashScopeAgent/0.1"},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("Web page read request timed out: url=%s", original_url)
            raise TimeoutError(f"Web page read request timed out after {self.timeout_seconds:g} seconds.") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Web page returned HTTP error: url=%s status=%s",
                original_url,
                exc.response.status_code,
            )
            raise ValueError(f"Web page returned HTTP {exc.response.status_code}.") from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Web page read request failed: url=%s error=%s",
                original_url,
                exc.__class__.__name__,
            )
            raise ConnectionError("Unable to read web page.") from exc
        except Exception as exc:
            logger.exception("Unexpected web page read error: url=%s", original_url)
            raise RuntimeError("Unexpected web page read error.") from exc

        try:
            content_type = response.headers.get("content-type", "")
            raw_text = response.text
            if "html" in content_type.lower():
                text = self._extract_html_text(raw_text, str(response.url))
            else:
                text = raw_text

            raw_content_length = len(text)
            text = self._clean_text(text)
            if len(text) > self.max_content_chars:
                text = text[: self.max_content_chars - 3].rstrip() + "..."
            logger.info(
                "Web page content trimmed: url=%s raw_length=%s trimmed_length=%s",
                original_url,
                raw_content_length,
                len(text),
            )
        except Exception as exc:
            logger.exception("Unexpected web page content parsing error: url=%s", original_url)
            raise RuntimeError("Unexpected web page content parsing error.") from exc

        result = {
            "url": str(response.url),
            "content_type": content_type,
            "content": text,
            "content_length": len(text),
            "cached": False,
        }
        self._set_cached_result(cache_key, result)
        return result

    def _extract_html_text(self, html: str, url: str) -> str:
        text = self._extract_with_trafilatura(html, url)
        if text:
            return text

        parser = _ReadableHTMLParser()
        parser.feed(html)
        return parser.text()

    def _normalize_timeout(self, value: float | int | None, default: float) -> float:
        try:
            timeout = float(value) if value is not None else default
        except (TypeError, ValueError):
            return default
        return max(timeout, 0.1)

    def _extract_with_trafilatura(self, html: str, url: str) -> str:
        if trafilatura is None:
            return ""

        try:
            text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
        except Exception as exc:
            logger.info(
                "Trafilatura extraction failed, falling back to HTMLParser: url=%s error=%s",
                url,
                exc.__class__.__name__,
            )
            return ""

        return str(text or "").strip()

    def _clean_text(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            clean_line = " ".join(line.split())
            if clean_line:
                lines.append(clean_line)
        return "\n\n".join(lines)

    def _normalize_url(self, url: str) -> str:
        parts = urlsplit(url.strip())
        path = parts.path or "/"
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                path,
                parts.query,
                "",
            )
        )

    def _get_cached_result(self, cache_key: str) -> dict[str, Any] | None:
        now = time()
        with _WEB_READER_CACHE_LOCK:
            cached = _WEB_READER_CACHE.get(cache_key)
            if cached is None:
                return None

            cached_at, result = cached
            if now - cached_at > WEB_READER_CACHE_TTL_SECONDS:
                logger.info("Web reader cache expired: url=%s", cache_key)
                del _WEB_READER_CACHE[cache_key]
                return None

            return dict(result)

    def _set_cached_result(self, cache_key: str, result: dict[str, Any]) -> None:
        with _WEB_READER_CACHE_LOCK:
            _WEB_READER_CACHE[cache_key] = (time(), dict(result))
            while len(_WEB_READER_CACHE) > WEB_READER_CACHE_MAX_SIZE:
                oldest_key = min(_WEB_READER_CACHE, key=lambda key: _WEB_READER_CACHE[key][0])
                del _WEB_READER_CACHE[oldest_key]


class ReadWebpageTool(WebReaderTool):
    """Alias for WebReaderTool using the registry-facing read_webpage name."""

    name = "read_webpage"
    description = "Read a web page and extract readable text."
