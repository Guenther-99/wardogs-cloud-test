#!/usr/bin/env python3
"""Read-only connectivity checks. No secrets, Discord writes, or Steam login."""
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

TARGETS = [
    ('github_pages', os.environ.get('WARDOGS_PUBLIC_PAGE', 'https://guenther-99.github.io/wardogs-join/server.html')),
    ('steam_public', os.environ.get('WARDOGS_STEAM_PUBLIC_PROFILE', 'https://steamcommunity.com/profiles/76561199685613122/')),
]

def probe(name, url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in {'guenther-99.github.io', 'steamcommunity.com'}:
        raise ValueError('Disallowed URL for ' + name)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; WARDOGS-cloud-smoke/1.0)', 'Accept': 'text/html'})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            code = response.status
            body = response.read(250000)
        seconds = round(time.monotonic() - start, 2)
        print(f'{name}: HTTP {code} | {seconds}s | payload_bytes={len(body)}')
        if name == 'github_pages' and code == 200:
            return True
        if name == 'steam_public':
            print('steam_public: Anonymous response only; it DOES NOT prove Steam lobby detection or authenticated access.')
            return True
        return False
    except urllib.error.HTTPError as exc:
        print(f'{name}: HTTP {exc.code}; remote service may restrict GitHub-hosted runners.')
        # Only GitHub Pages is required for basic smoke success; Steam rate-limiting is valuable diagnostic, not fatal.
        return name == 'steam_public'
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f'{name}: network error ({type(exc).__name__})')
        return name == 'steam_public'


def main():
    checks = [(name, probe(name, url)) for name, url in TARGETS]
    failed = [name for name, ok in checks if not ok]
    if failed:
        print('RESULT: FAIL basic cloud reachability: ' + ', '.join(failed))
        return 1
    print('RESULT: PASS basic GitHub Pages reachability. No Discord writes or Steam authentication tested.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
