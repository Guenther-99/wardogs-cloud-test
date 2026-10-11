"""PATCH only an existing Discord webhook message, gated by explicit manual workflow input.
No POST/DELETE; no persistence of webhook or message ID.
"""
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent

def prepare():
    messages = json.loads((ROOT / 'preview.json').read_text(encoding='utf-8'))
    if len(messages) != 1:
        raise RuntimeError('Safety stop: cloud currently requires exactly ONE existing Discord message')
    payload = messages[0]
    if not isinstance(payload.get('embeds'), list):
        raise RuntimeError('No embeds in preview')
    # Cloud has no fresh local Steam data. Explicitly label this section instead of using a stale join link.
    for embed in payload['embeds']:
        if 'FREUNDE ZUM BEITRETEN' in embed.get('title', ''):
            embed['description'] = '_Steam-Lobbys werden weiterhin vom lokalen V5.1-Collector verwaltet. In der Cloud noch nicht verfügbar._'
    payload['allowed_mentions'] = {'parse': []}
    return payload

def main():
    if os.environ.get('WARDOGS_CONFIRM', '') != 'PUBLISH':
        raise RuntimeError('Safety stop: only explicit PUBLISH can write to Discord')
    webhook = os.environ.get('DISCORD_WEBHOOK_URL', '').strip().rstrip('/')
    message_id = os.environ.get('DISCORD_MESSAGE_ID', '').strip()
    if not re.fullmatch(r'https://(?:discord|discordapp)\.com/api/webhooks/\d+/[A-Za-z0-9._-]+', webhook):
        raise RuntimeError('Missing or malformed DISCORD_WEBHOOK_URL GitHub Actions Secret')
    if not re.fullmatch(r'\d{15,22}', message_id):
        raise RuntimeError('Missing or malformed DISCORD_MESSAGE_ID GitHub Actions Secret')
    payload = prepare()
    # GET first: 404 means wrong message ID, do not create anything.
    url = webhook + '/messages/' + message_id
    req = urllib.request.Request(url, headers={'User-Agent':'WardogsCloudCutover/6.0','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            current = json.load(resp)
        if str(current.get('id')) != message_id:
            raise RuntimeError('Discord returned unexpected message ID')
    except urllib.error.HTTPError as e:
        raise RuntimeError('Could not read existing Discord message (HTTP %d). Nothing published.' % e.code) from None
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='PATCH', headers={'User-Agent':'WardogsCloudCutover/6.0','Content-Type':'application/json','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.load(resp)
            if str(result.get('id')) != message_id:
                raise RuntimeError('Unexpected message ID after PATCH')
    except urllib.error.HTTPError as e:
        raise RuntimeError('Discord rejected PATCH (HTTP %d). No new message was created.' % e.code) from None
    print('PASS: existing Discord message edited via PATCH; no POST or DELETE; id was not logged.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FAILED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
