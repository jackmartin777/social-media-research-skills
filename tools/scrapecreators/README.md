# ScrapeCreators scraping CLI

One command-line tool (and Python library) for scraping public data from TikTok, Instagram, YouTube, Facebook, X/Twitter, Reddit, LinkedIn, Threads, Bluesky, Pinterest, Snapchat, Twitch, ad libraries and more. It covers all 196 GET endpoints in the [ScrapeCreators API](https://docs.scrapecreators.com/). It needs Python 3.8+ and has no third-party dependencies.

## Setup

```bash
export SCRAPECREATORS_API_KEY=sk_...   # https://scrapecreators.com
cd tools
```

## Usage

```bash
python3 -m scrapecreators list                      # platforms
python3 -m scrapecreators list tiktok               # commands for a platform
python3 -m scrapecreators describe tiktok profile-videos   # params + docs

python3 -m scrapecreators tiktok profile --handle charlidamelio
python3 -m scrapecreators youtube channel-videos --handle MrBeast --all-pages --max-pages 5 --format csv -o videos.csv
python3 -m scrapecreators facebook ad-library-search-ads --query "running shoes" --country US
python3 -m scrapecreators reddit post-comments --url https://www.reddit.com/r/... --format jsonl
```

- Command names come from the API path: `/v3/tiktok/profile/videos` → `tiktok profile-videos`. Use `list` to see them.
- Parameters are passed as `--name value` (or `--name=value`). `-` and `_` are interchangeable, and required params are checked before any call is made.
- Aliases: `x`=twitter, `tt`=tiktok, `ig`=instagram, `yt`=youtube, `fb`=facebook.
- `--all-pages` follows the response's pagination token (`cursor`, `max_cursor`, `continuationToken`, etc.), up to `--max-pages` (default 10). Each page costs credits.
- `--format json|jsonl|csv`. jsonl and csv extract the main list of records from the response, and csv flattens nested fields.
- Errors go to stderr and the exit code is 1. 429 and 5xx responses are retried with backoff.

## As a library

```python
from scrapecreators import Client
c = Client()  # reads SCRAPECREATORS_API_KEY
profile = c.get("/v1/tiktok/profile", {"handle": "charlidamelio"})
for page in c.paginate("/v3/tiktok/profile/videos", {"handle": "charlidamelio"}, max_pages=3):
    ...
```

## Maintenance

`endpoints.json` is generated from the OpenAPI spec. To refresh it:

```bash
python3 scrapecreators/gen_endpoints.py        # fetches https://docs.scrapecreators.com/openapi.json
```

Tests:

```bash
python3 -m unittest discover -s scrapecreators/tests
```

This tool only works with public data.
