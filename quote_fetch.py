#!/usr/bin/env python3
"""Fetch BrainyQuote's Funny Quote of the Day and write quote.json.

Runs in GitHub Actions (see .github/workflows/quote.yml). Stdlib only.
On any failure -- network, markup change, validation -- it exits
nonzero WITHOUT touching quote.json, so the last good quote keeps
serving and the failed run shows up red in the Actions tab.

Resilience (added after the Oct 24 AM runs failed twice while the
same fetch worked elsewhere -- GitHub's datacenter IPs get bot
challenges that a single request can't ride out): each run tries
up to 3 rounds across two browser user agents, with a growing
sleep between rounds, and logs exactly which stage failed so the
next failed run's log names the cause instead of guessing.
"""
import html as htmlmod
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

URL = "https://www.brainyquote.com/quote_of_the_day"
UAS = [
    ("iphone",
     "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
     "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
     "Mobile/15E148 Safari/604.1"),
    ("chrome",
     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
     "AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/130.0.0.0 Safari/537.36"),
]
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


def fetch_quote():
    """(quote, author) via retries + UA fallback, or None.

    A bot-challenge page usually arrives as a non-200, or as a 200
    whose markup has no Funny block -- both are treated as "try the
    next agent", never as a reason to clobber quote.json."""
    last_err = "no attempt made"
    for attempt in range(3):
        for label, ua in UAS:
            try:
                req = urllib.request.Request(URL, headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                })
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status != 200:
                        print(f"Round {attempt + 1} ({label}): HTTP {resp.status}", file=sys.stderr)
                        last_err = f"HTTP {resp.status}"
                        continue
                    page = resp.read().decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                print(f"Round {attempt + 1} ({label}): HTTP {e.code}", file=sys.stderr)
                last_err = f"HTTP {e.code}"
                continue
            except Exception as e:
                print(f"Round {attempt + 1} ({label}): {type(e).__name__}: {e}", file=sys.stderr)
                last_err = f"{type(e).__name__}: {e}"
                continue
            got = parse_brainy(page)
            if got:
                return got
            print(f"Round {attempt + 1} ({label}): page fetched but no Funny quote found", file=sys.stderr)
            last_err = "parse failed"
        if attempt < 2:
            time.sleep(20 * (attempt + 1))
    print(f"All fetch attempts failed (last: {last_err})", file=sys.stderr)
    return None


def main():
    got = fetch_quote()
    if not got:
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
