from html.parser import HTMLParser
import re
from typing import Any

import httpx

from app.core.logger import get_logger


logger = get_logger(__name__)


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


class WebReaderTool:
    """Fetch a web page and return readable text."""

    name = "web_reader"
    description = "Read a web page and extract readable text."
    timeout_seconds = 5.0
    max_content_chars = 3000

    def run(self, url: str) -> dict[str, Any]:
        url = url.strip()
        if not url:
            raise ValueError("URL is empty.")
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://.")

        try:
            response = httpx.get(
                url,
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 DashScopeAgent/0.1"},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("Web page read request timed out: url=%s", url)
            raise TimeoutError("Web page read request timed out after 5 seconds.") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Web page returned HTTP error: url=%s status=%s",
                url,
                exc.response.status_code,
            )
            raise ValueError(f"Web page returned HTTP {exc.response.status_code}.") from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Web page read request failed: url=%s error=%s",
                url,
                exc.__class__.__name__,
            )
            raise ConnectionError("Unable to read web page.") from exc
        except Exception as exc:
            logger.exception("Unexpected web page read error: url=%s", url)
            raise RuntimeError("Unexpected web page read error.") from exc

        try:
            content_type = response.headers.get("content-type", "")
            raw_text = response.text
            if "html" in content_type.lower():
                parser = _ReadableHTMLParser()
                parser.feed(raw_text)
                text = parser.text()
            else:
                text = raw_text

            raw_content_length = len(text)
            text = self._clean_text(text)
            if len(text) > self.max_content_chars:
                text = text[: self.max_content_chars - 3].rstrip() + "..."
            logger.info(
                "Web page content trimmed: url=%s raw_length=%s trimmed_length=%s",
                url,
                raw_content_length,
                len(text),
            )
        except Exception as exc:
            logger.exception("Unexpected web page content parsing error: url=%s", url)
            raise RuntimeError("Unexpected web page content parsing error.") from exc

        return {
            "url": str(response.url),
            "content_type": content_type,
            "content": text,
            "content_length": len(text),
        }

    def _clean_text(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            clean_line = " ".join(line.split())
            if clean_line:
                lines.append(clean_line)
        return "\n\n".join(lines)
