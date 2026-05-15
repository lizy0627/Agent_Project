import os
from typing import Any

import httpx


class WebSearchTool:
    """Search the web through the Tavily Search API."""

    name = "web_search"
    description = "Search the web for current information."
    endpoint = "https://api.tavily.com/search"
    timeout_seconds = 15.0

    def __init__(self, api_key: str | None = None, provider: str | None = None) -> None:
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.provider = provider or os.getenv("WEB_SEARCH_PROVIDER", "tavily")

    def run(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("Search query is empty.")

        if self.provider != "tavily":
            raise ValueError(f"Unsupported web search provider: {self.provider}")

        if not self.api_key:
            raise ValueError("TAVILY_API_KEY is not configured.")

        safe_max_results = min(max(int(max_results), 1), 10)
        safe_search_depth = search_depth if search_depth in {"basic", "advanced"} else "basic"

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": safe_search_depth,
            "max_results": safe_max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        try:
            response = httpx.post(self.endpoint, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError("Tavily search request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc.response)
            raise ValueError(f"Tavily API returned an error: {detail}") from exc
        except httpx.RequestError as exc:
            raise ConnectionError("Unable to connect to Tavily Search API.") from exc
        except ValueError as exc:
            raise ValueError("Tavily API returned invalid JSON.") from exc

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "snippet": item.get("content", ""),
                "score": item.get("score"),
            }
            for item in data.get("results", [])
            if isinstance(item, dict)
        ]

        return {
            "query": data.get("query", query),
            "results": results,
        }

    def _extract_error_detail(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return f"HTTP {response.status_code}"

        if isinstance(data, dict):
            detail = data.get("detail") or data.get("error") or data.get("message")
            if detail:
                return str(detail)

        return f"HTTP {response.status_code}"
