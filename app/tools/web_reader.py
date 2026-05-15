from html.parser import HTMLParser
from typing import Any

import httpx


class _ReadableHTMLParser(HTMLParser):
    """Extract readable text from common HTML pages."""

    ignored_tags = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.ignored_tags:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.ignored_tags and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return

        text = " ".join(data.split())
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return "\n".join(self._chunks)


class WebReaderTool:
    """Fetch a web page and return readable text."""

    name = "web_reader"
    description = "Read a web page and extract readable text."
    timeout_seconds = 15.0
    max_content_chars = 12000

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
            raise TimeoutError("Web page read request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"Web page returned HTTP {exc.response.status_code}.") from exc
        except httpx.RequestError as exc:
            raise ConnectionError("Unable to read web page.") from exc

        content_type = response.headers.get("content-type", "")
        raw_text = response.text
        if "html" in content_type.lower():
            parser = _ReadableHTMLParser()
            parser.feed(raw_text)
            text = parser.text()
        else:
            text = raw_text

        text = " ".join(text.split())
        if len(text) > self.max_content_chars:
            text = text[: self.max_content_chars].rstrip() + "..."

        return {
            "url": str(response.url),
            "content_type": content_type,
            "content": text,
            "content_length": len(text),
        }
