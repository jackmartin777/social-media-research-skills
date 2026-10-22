"""Minimal ScrapeCreators API client (standard library only)."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.scrapecreators.com"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ScrapeCreatorsError(Exception):
    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


class Client:
    def __init__(self, api_key=None, base_url=BASE_URL, retries=3, timeout=120):
        self.api_key = api_key or os.environ.get("SCRAPECREATORS_API_KEY")
        if not self.api_key:
            raise ScrapeCreatorsError(
                "Missing API key. Set SCRAPECREATORS_API_KEY (get one at https://scrapecreators.com)."
            )
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.timeout = timeout

    def get(self, path, params=None):
        query = urllib.parse.urlencode(
            {k: v for k, v in (params or {}).items() if v is not None}
        )
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        req = urllib.request.Request(
            url, headers={"x-api-key": self.api_key, "Accept": "application/json"}
        )
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                if e.code in RETRY_STATUSES and attempt < self.retries:
                    time.sleep(2**attempt)
                    continue
                raise ScrapeCreatorsError(f"HTTP {e.code} from {path}: {body[:500]}", e.code, body)
            except urllib.error.URLError as e:
                if attempt < self.retries:
                    time.sleep(2**attempt)
                    continue
                raise ScrapeCreatorsError(f"Network error: {e.reason}")

    def paginate(self, path, params=None, max_pages=10, accepted=None):
        """Yield each page, following the pagination token in the response.

        `accepted` is the set of query params the endpoint takes; the next-page
        token is only followed if the endpoint accepts it as a parameter.
        """
        params = dict(params or {})
        seen = set()
        for _ in range(max_pages):
            page = self.get(path, params)
            yield page
            key, token = next_cursor(page, accepted)
            if not token or (key, str(token)) in seen:
                return
            seen.add((key, str(token)))
            params[key] = token


PAGINATION_KEYS = (
    "cursor",
    "max_cursor",
    "continuationToken",
    "next_max_id",
    "max_id",
    "next_page_id",
    "after",
    "pageToken",
    "paginationToken",
)


def next_cursor(page, accepted=None):
    """Return (param_name, value) for the next page, or (None, None)."""
    if not isinstance(page, dict) or page.get("has_more") is False or page.get("has_next_page") is False:
        return None, None
    for key in PAGINATION_KEYS:
        if accepted is not None and key not in accepted:
            continue
        value = page.get(key)
        if value not in (None, "", 0, False):
            return key, value
    return None, None
