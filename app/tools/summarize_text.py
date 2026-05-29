import re

from app.tools.base import BaseTool


class SummarizeTextTool(BaseTool):
    """Create a short extractive summary for a text block."""

    name = "summarize_text"
    description = "Summarize a piece of text."
    args_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to summarize.",
            },
            "max_sentences": {
                "type": "integer",
                "default": 3,
            },
            "max_chars": {
                "type": "integer",
                "default": 500,
            },
        },
        "required": ["text"],
    }

    def run(self, text: str, max_sentences: int = 3, max_chars: int = 500) -> dict[str, object]:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            raise ValueError("Text is empty.")

        sentences = self._split_sentences(text)
        selected = sentences[: max(1, max_sentences)]
        summary = " ".join(selected).strip()

        if len(summary) > max_chars:
            summary = summary[:max_chars].rstrip() + "..."

        return {
            "summary": summary,
            "original_length": len(text),
            "summary_length": len(summary),
        }

    def _split_sentences(self, text: str) -> list[str]:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？.!?])\s*", text)
            if sentence.strip()
        ]
        return sentences or [text]
