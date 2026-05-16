from copy import deepcopy
import os
from threading import Lock
from time import time
from typing import Any

import httpx

from app.core.logger import get_logger


logger = get_logger(__name__)
WEB_SEARCH_CACHE_TTL_SECONDS = 3 * 60
WEB_SEARCH_CACHE_MAX_SIZE = 100
_WEB_SEARCH_CACHE: dict[str, tuple[float, dict]] = {}
_WEB_SEARCH_CACHE_LOCK = Lock()


class WebSearchTool:
    """Search the web through the Tavily Search API."""

    name = "web_search"
    description = "Search the web for current information."
    endpoint = "https://api.tavily.com/search"
    timeout_seconds = 5.0

    def __init__(self, api_key: str | None = None, provider: str | None = None) -> None:
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.provider = provider or os.getenv("WEB_SEARCH_PROVIDER", "tavily")

    def run(
        self,
        query: str,
        max_results: int = 3,
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
        cache_key = self._cache_key(query, safe_max_results, safe_search_depth)
        cached_result = self._get_cached_result(cache_key)
        if cached_result is not None:
            logger.info(
                "Web search cache hit: query=%s max_results=%s search_depth=%s",
                query[:200],
                safe_max_results,
                safe_search_depth,
            )
            return {**cached_result, "cached": True}

        logger.info(
            "Web search cache miss: query=%s max_results=%s search_depth=%s",
            query[:200],
            safe_max_results,
            safe_search_depth,
        )

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
            if not isinstance(data, dict):
                raise ValueError("Tavily API returned a non-object JSON response.")
        except httpx.TimeoutException as exc:
            logger.warning("Tavily search request timed out: query=%s", query[:200])
            raise TimeoutError("Tavily search request timed out after 5 seconds.") from exc
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc.response)
            logger.warning(
                "Tavily search API returned an error: status=%s detail=%s",
                exc.response.status_code,
                detail,
            )
            raise ValueError(f"Tavily API returned an error: {detail}") from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Tavily search request failed: query=%s error=%s",
                query[:200],
                exc.__class__.__name__,
            )
            raise ConnectionError("Unable to connect to Tavily Search API.") from exc
        except ValueError as exc:
            logger.warning("Tavily search returned invalid JSON: query=%s", query[:200])
            raise ValueError("Tavily API returned invalid JSON.") from exc
        except Exception as exc:
            logger.exception("Unexpected Tavily search error: query=%s", query[:200])
            raise RuntimeError("Unexpected Tavily search error.") from exc

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

        result = {
            "query": data.get("query", query),
            "results": results,
            "cached": False,
        }
        self._set_cached_result(cache_key, result)
        return result

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

    def _cache_key(self, query: str, max_results: int, search_depth: str) -> str:
        normalized_query = " ".join(query.split()).casefold()
        return f"{normalized_query}\n{max_results}\n{search_depth}"

    def _get_cached_result(self, cache_key: str) -> dict[str, Any] | None:
        now = time()
        with _WEB_SEARCH_CACHE_LOCK:
            cached = _WEB_SEARCH_CACHE.get(cache_key)
            if cached is None:
                return None

            cached_at, result = cached
            if now - cached_at > WEB_SEARCH_CACHE_TTL_SECONDS:
                logger.info("Web search cache expired: key=%s", self._safe_cache_key_for_log(cache_key))
                del _WEB_SEARCH_CACHE[cache_key]
                return None

            return deepcopy(result)

    def _set_cached_result(self, cache_key: str, result: dict[str, Any]) -> None:
        with _WEB_SEARCH_CACHE_LOCK:
            _WEB_SEARCH_CACHE[cache_key] = (time(), deepcopy(result))
            while len(_WEB_SEARCH_CACHE) > WEB_SEARCH_CACHE_MAX_SIZE:
                oldest_key = min(_WEB_SEARCH_CACHE, key=lambda key: _WEB_SEARCH_CACHE[key][0])
                del _WEB_SEARCH_CACHE[oldest_key]

    def _safe_cache_key_for_log(self, cache_key: str) -> str:
        query, max_results, search_depth = cache_key.split("\n", 2)
        return f"query={query[:200]} max_results={max_results} search_depth={search_depth}"
