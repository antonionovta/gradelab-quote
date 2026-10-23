#!/usr/bin/env python3
"""Fetch BrainyQuote's Funny Quote of the Day and write quote.json.

Runs in GitHub Actions (see .github/workflows/quote.yml). Stdlib only.
On any failure -- network, markup change, validation -- it exits
nonzero WITHOUT touching quote.json, so the last good quote keeps
serving and the failed run shows up red in the Actions tab.
"""
import html as htmlmod
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

URL = "https://www.brainyquote.com/quote_of_the_day"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
      "Mobile/15E148 Safari/604.1")
OUT = "quote.json"


def _clean(text):
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", htmlmod.unescape(text)).strip()


def _anchors(fragment):
    return [_clean(m) for m in re.findall(r"<a[^>]*>(.*?)</a>", fragment, re.S)]


def _pick(links):
    for i, t in enumerate(links):
        if 25 < len(t) < 220:
            if i + 1 < len(links) and 1 < len(links[i + 1]) < 60:
                return t, links[i + 1]
    return None


def parse_brainy(page):
    """(quote, author) for the Funny Quote of the Day, or None.
    Mirrors the app's parser: find the Funny Quote heading, walk the
    block after it for the first long link (the quote) and the link
    after it (the author); fall back to the page's quote links."""
    idx = page.lower().find("funny quote of the day")
    if idx >= 0:
        got = _pick(_anchors(page[idx:idx + 9000]))
        if got:
            return got
    links = []
    for href, text in re.findall(r'<a[^>]+href="(/quotes/[^"]*)"[^>]*>(.*?)</a>', page, re.S):
        links.append(_clean(text))
    return _pick(links)


def fetch_page():
    """GET the quote-of-the-day page, retrying transient blocks.
    BrainyQuote's bot wall intermittently 403s datacenter IPs
    (GitHub's runners included); a retry a minute later, or the
    next scheduled run on a fresh runner, usually gets through."""
    headers = {"User-Agent": UA,
               "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "en-US,en;q=0.9"}
    last = None
    for attempt, wait in enumerate((0, 30, 90)):
        if wait:
            time.sleep(wait)
        try:
            req = urllib.request.Request(URL, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    print(f"attempt {attempt + 1}: HTTP {resp.status}", file=sys.stderr)
                    continue
                return resp.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            print(f"attempt {attempt + 1}: {e}", file=sys.stderr)
    if last:
        raise last
    return None


def main():
    fetch_err = None
    try:
        page = fetch_page()
    except Exception as e:
        page, fetch_err = None, e
    if not page:
        # Nothing to fetch with -- but if quote.json already
        # carries today's quote, this run has nothing to do:
        # stand down quietly instead of failing red.
        today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        try:
            with open(OUT, encoding="utf-8") as f:
                old = json.load(f)
            if old.get("date") == today:
                print(f"fetch failed ({fetch_err}) but quote.json already has today's quote; standing down")
                return 0
        except Exception:
            pass
        print(f"fetch failed: {fetch_err}", file=sys.stderr)
        return 1
    got = parse_brainy(page)
    if not got:
        print("Could not parse the Funny Quote of the Day -- markup may have changed", file=sys.stderr)
        return 1
    quote, author = got
    data = {
        "quote": quote,
        "author": author,
        "date": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d"),
        "source": "BrainyQuote Funny Quote of the Day",
    }
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        if old.get("quote") == quote and old.get("author") == author and old.get("date") == data["date"]:
            print("quote.json already current; nothing to write")
            return 0
    except Exception:
        pass
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {OUT}: {quote!r} - {author} ({data['date']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
