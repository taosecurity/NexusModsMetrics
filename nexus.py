"""Tiny helper for the Nexus Mods GraphQL v2 API (no API key needed for game and mod counts).

Nexus asks every client to identify itself with Application-Name and Application-Version headers
(API acceptable use policy). Standard library only, so it runs on Windows, Linux, FreeBSD and GitHub Actions.
"""
import json
import time
import urllib.error
import urllib.request

API = "https://api.nexusmods.com/v2/graphql"
APP_NAME = "NexusModsMetrics"
APP_VERSION = "0.1.0"
DELAY = 1.0  # seconds between requests, to be polite
_last = [0.0]


def query(gql, variables=None, tries=4):
    """POST one GraphQL query and return its "data" dict. Raises RuntimeError on API errors."""
    body = json.dumps({"query": gql, "variables": variables or {}}).encode("utf-8")
    for attempt in range(1, tries + 1):
        wait = DELAY - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(API, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Application-Name": APP_NAME,
            "Application-Version": APP_VERSION,
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                _last[0] = time.time()
                out = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            _last[0] = time.time()
            if attempt == tries:
                raise RuntimeError(f"Nexus API request failed after {tries} tries: {e}")
            time.sleep(5 * attempt)
            continue
        if out.get("errors"):
            raise RuntimeError("Nexus API error: " + json.dumps(out["errors"])[:500])
        return out["data"]


GAMES_Q = """query($count: Int!) {
  games(count: $count, sort: [{downloads: {direction: DESC}}]) {
    totalCount
    nodes { id name domainName downloadCount uniqueDownloadCount modCount collectionCount approvedAt }
  }
}"""


def top_games(count=40):
    """Games sorted by total downloads, biggest first."""
    return query(GAMES_Q, {"count": count})["games"]["nodes"]
