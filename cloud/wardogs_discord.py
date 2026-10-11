"""WARDOGS Discord V3. Python 3.10+, standard library only."""
import argparse
import datetime as dt
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
API = 'https://api.wardogservers.com/v1/snapshot'
JOIN_URL = re.compile(r'^steam://joinlobby/1867240/([0-9]{1,20})/([0-9]{17})$', re.I)
UUID = re.compile(r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$', re.I)
STEAM_OUTPUT = Path(os.environ.get('WARDOGS_STEAM_JSON', str(ROOT / 'steam_lobbies.json')))
STEAM_MAX_AGE_MINUTES = 15
FRIENDS_COLOR = 0x9b59b6
GROUPS = [('regular', '🟢 REGULAR', 0x2ecc71), ('infantry', '🔵 INFANTRY ONLY', 0x3498db), ('mixed', '🟠 MIXED', 0xf39c12), ('unknown', '⚪ NICHT ERKANNT', 0x95a5a6)]


def read_json(name, default=None):
    p = ROOT / name
    if not p.exists():
        if default is not None:
            return default
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding='utf-8-sig'))


def write_json(name, value):
    p = ROOT / name
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(p)


def http_json(url, method='GET', payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    headers = {'Accept': 'application/json', 'User-Agent': 'WardogsCommunityBoard/3.0'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, method=method, headers=headers), timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = min(30, int(e.headers.get('Retry-After', '3')))
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            delay = 2 ** attempt + 1
        time.sleep(delay)
    raise RuntimeError('API-Abfrage fehlgeschlagen')


def clean(value, limit=500):
    s = str(value or '').replace('@', '@\u200b').replace('`', "'").replace('\r', ' ').replace('\n', ' ').strip()
    s = s.replace('**', '').replace('||', '')
    return s[:limit]


def mode(server):
    if not server:
        return None
    rules = server.get('rulesets') or []
    mods = (server.get('mode') or {}).get('modifiers') or []
    if 'infantry-only' in rules or 'KOTH_InfantryOnly' in mods:
        return 'infantry'
    if 'standard' in rules:
        return 'regular'
    return None


def category(item, history, server):
    forced = item.get('category', 'auto')
    if forced in ('regular', 'infantry', 'mixed'):
        return forced
    seen = history.get(item['id'].lower(), [])
    if 'regular' in seen and 'infantry' in seen:
        return 'mixed'
    return mode(server) or 'unknown'


def server_line(item, server, online, history, fresh):
    sid = item['id'].lower()
    name = clean(item.get('label') or (server or {}).get('name') or 'Unbekannter Server', 130)
    number = (server or {}).get('players') if online and fresh else None
    maximum = (server or {}).get('maxPlayers') if online and fresh else None
    users = f'{number}/{maximum}' if number is not None and maximum is not None else '–/–'
    server_page = 'https://guenther-99.github.io/wardogs-join/server.html?' + urlencode({'id': sid, 'name': name})
    shown = f'**{name}**  ·  👥 {users}\n`{sid}` · [🔗 Servercode öffnen]({server_page})'
    if category(item, history, server) == 'mixed':
        actual = mode(server) if online and fresh else None
        shown += '\n🔄 Aktuell: ' + {'regular':'Regular','infantry':'Infantry Only'}.get(actual, 'nicht bekannt')
    join_url = str(item.get('steam_join_url') or '').strip()
    # Alte manuelle Freundeshinweise nicht doppelt anzeigen.
    note = clean(item.get('note'), 300)
    if note:
        shown += '\n📝 ' + note
    return shown


def friend_embed():
    """Separate join links; never guess a WARDOGS server from a Steam lobby."""
    if not STEAM_OUTPUT.is_file():
        return {'title': '🎮 FREUNDE ZUM BEITRETEN', 'description':
                '_Steam-Collector noch nicht eingerichtet oder keine Ergebnisdatei gefunden._', 'color': FRIENDS_COLOR}
    try:
        obj = json.loads(STEAM_OUTPUT.read_text(encoding='utf-8-sig'))
        observed = dt.datetime.fromisoformat(obj['observed_at'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            return {'title': '🎮 FREUNDE ZUM BEITRETEN', 'description': '_Steam-Daten haben keine gültige Zeitzone._', 'color': FRIENDS_COLOR}
        age = (dt.datetime.now(dt.timezone.utc) - observed.astimezone(dt.timezone.utc)).total_seconds()
        if not -120 <= age <= STEAM_MAX_AGE_MINUTES * 60:
            return {'title': '🎮 FREUNDE ZUM BEITRETEN', 'description':
                    '_Keine aktuellen Steam-Daten (Collector älter als 15 Minuten)._', 'color': FRIENDS_COLOR}
        players = obj.get('players') or []
        lines = []
        for p in players:
            if p.get('status') != 'found':
                continue
            sid = str(p.get('steam_id') or '')
            lobby = str(p.get('lobby_id') or '')
            if not (re.fullmatch(r'7656119\d{10}', sid) and re.fullmatch(r'\d{10,20}', lobby)):
                continue
            friend = clean(p.get('friend') or p.get('discord') or 'Steam-Freund', 65)
            # Rebuild HTTPS link from validated values rather than trusting arbitrary JSON URLs.
            from urllib.parse import urlencode
            url = 'https://guenther-99.github.io/wardogs-join/?' + urlencode({
                'lobby': lobby, 'steamid': sid, 'friend': friend})
            lines.append('🟢 **' + friend + '** · [Spiel beitreten](' + url + ')')
        description = '\n'.join(lines) if lines else '_Zurzeit keine beitretbaren Freundeslobbys erkannt._'
        description += '\n\n*Kürzlich aus Steam gelesen · Beitritt abhängig von Lobby und freien Plätzen.*'
        return {'title': '🎮 FREUNDE ZUM BEITRETEN', 'description': description[:3900], 'color': FRIENDS_COLOR}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
        logging.warning('Steam-Ergebnis konnte nicht eingelesen werden: %s', e)
        return {'title': '🎮 FREUNDE ZUM BEITRETEN', 'description':
                '_Steam-Ergebnisse momentan nicht verfügbar._', 'color': FRIENDS_COLOR}


def make_messages(config, state, current, fresh, timestamp):
    cached = state.get('last_seen', {})
    history = state.get('mode_history', {})
    buckets = {k: [] for k, _, _ in GROUPS}
    for item in config['servers']:
        sid = item['id'].lower()
        online = sid in current
        server = current.get(sid) or cached.get(sid)
        buckets[category(item, history, server)].append(server_line(item, server, online, history, fresh))
    title = clean(config.get('title') or 'WARDOGS | UNSERE SERVERLISTE', 150)
    intro = f'🎮 **{title}**\nAutomatisch alle 5 Minuten · Stand: {timestamp}'
    if not fresh:
        intro += '\n⚠️ API-Daten nicht aktuell'
    # Embed descriptions max 4096; total message embeds max 6000 chars.
    pages = []
    page_embeds = []
    total = 0
    for key, heading, color in GROUPS:
        if key == 'unknown' and not buckets[key]:
            continue
        entries = buckets[key] or ['_Keine Server_']
        blocks, chunk = [], ''
        for line in entries:
            if len(line) > 3700:
                raise ValueError('Server-Eintrag zu lang; Note verkürzen')
            if chunk and len(chunk) + len(line) + 2 > 3850:
                blocks.append(chunk)
                chunk = ''
            chunk += ('\n\n' if chunk else '') + line
        if chunk:
            blocks.append(chunk)
        for index, description in enumerate(blocks):
            embed = {'title': heading + (f' ({index+1}/{len(blocks)})' if len(blocks)>1 else ''),
                     'description': description, 'color': color}
            length = len(embed['title']) + len(description)
            if page_embeds and (total + length > 5600 or len(page_embeds) >= 10):
                pages.append(page_embeds)
                page_embeds, total = [], 0
            page_embeds.append(embed)
            total += length
    if page_embeds:
        pages.append(page_embeds)
    friends = friend_embed()
    length = len(friends['title']) + len(friends['description'])
    if not pages:
        pages = [[]]
    if len(pages[-1]) >= 10 or sum(len(e['title']) + len(e['description']) for e in pages[-1]) + length > 5600:
        pages.append([])
    pages[-1].append(friends)
    return [{'content': intro if i == 0 else '🎮 **WARDOGS | Fortsetzung**',
             'embeds': embeds, 'allowed_mentions': {'parse': []}} for i, embeds in enumerate(pages)]


def publish(webhook, messages, state):
    # Track each created message immediately; reuse old IDs on updates.
    original = list(state.get('message_ids', []))
    new = []
    for index, payload in enumerate(messages):
        if index < len(original):
            try:
                http_json(webhook.rstrip('/') + '/messages/' + str(original[index]), 'PATCH', payload)
                new.append(original[index])
                continue
            except urllib.error.HTTPError as err:
                if err.code != 404:
                    raise
        result = http_json(webhook.rstrip('/') + '?wait=true', 'POST', payload)
        if not result or 'id' not in result:
            raise RuntimeError('Discord lieferte keine Nachrichten-ID')
        new.append(result['id'])
        state['message_ids'] = new + original[len(new):]
        write_json('state.json', state)
    for mid in original[len(messages):]:
        try:
            http_json(webhook.rstrip('/') + '/messages/' + str(mid), 'DELETE')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                logging.warning('Alte Nachricht konnte nicht entfernt werden: %s', e)
    state['message_ids'] = new
    write_json('state.json', state)


def run(args):
    config = read_json('servers.json')
    items = config.get('servers')
    if not isinstance(items, list) or not items:
        raise ValueError('servers.json: mindestens ein Server erforderlich')
    ids = [str(i.get('id', '')).lower() for i in items]
    if len(set(ids)) != len(ids) or not all(UUID.fullmatch(i) for i in ids):
        raise ValueError('Doppelte oder ungültige Server-IDs')
    for item in items:
        join_url = str(item.get('steam_join_url') or '').strip()
        if join_url and not JOIN_URL.fullmatch(join_url):
            raise ValueError('Ungültiger Steam-Join-Link für '+str(item['id']))
    state = read_json('state.json', {})
    snapshot = read_json(args.snapshot_file) if args.snapshot_file else http_json(API)
    if not isinstance(snapshot.get('data'), list):
        raise ValueError('API-Snapshot enthält keine data-Liste')
    fresh = not (snapshot.get('meta') or {}).get('stale', False)
    current = {str(s.get('serverId')).lower():s for s in snapshot['data'] if s.get('serverId')} if fresh else {}
    # Preview must not touch live state: work on a detached copy.
    working = json.loads(json.dumps(state))
    if fresh:
        history = working.setdefault('mode_history', {})
        cached = working.setdefault('last_seen', {})
        for sid in ids:
            server = current.get(sid)
            if server:
                cached[sid] = server
                detected = mode(server)
                if detected:
                    history[sid] = sorted(set(history.get(sid, [])) | {detected})
    try:
        from zoneinfo import ZoneInfo
        stamp = dt.datetime.now(ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y %H:%M')
    except Exception:
        stamp = dt.datetime.now().astimezone().strftime('%d.%m.%Y %H:%M')
    messages = make_messages(config, working, current, fresh, stamp)
    if args.preview:
        preview = ROOT / 'preview.json'
        preview.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = [m['content']+'\n\n'+'\n\n'.join(e['title']+'\n'+e['description'] for e in m['embeds']) for m in messages]
        (ROOT / 'preview.txt').write_text('\n\n---- Nächste Nachricht ----\n\n'.join(lines), encoding='utf-8')
        print('Vorschau erstellt: preview.txt und preview.json (keine Discord-Veröffentlichung).')
        return
    cfg = read_json('webhook.json')
    webhook = cfg.get('webhook_url', '').strip()
    if not webhook.startswith(('https://discord.com/api/webhooks/', 'https://discordapp.com/api/webhooks/')):
        raise ValueError('Webhook-Konfiguration fehlt oder ist ungültig')
    # Save learned state only after successful API call; publish retains message IDs.
    state.update({k:working[k] for k in ('last_seen','mode_history') if k in working})
    publish(webhook, messages, state)
    logging.info('Discord aktualisiert: %d Server, %d Nachricht(en)',len(ids),len(messages))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview',action='store_true')
    ap.add_argument('--snapshot-file',help='Lokaler API-Snapshot')
    args = ap.parse_args()
    (ROOT/'logs').mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(ROOT/'logs'/'wardogs.log',maxBytes=2000000,backupCount=3,encoding='utf-8'),logging.StreamHandler(sys.stdout)],format='%(asctime)s %(levelname)s %(message)s')
    try:
        run(args)
    except Exception:
        logging.exception('V3-Update fehlgeschlagen')
        sys.exit(1)

if __name__ == '__main__':
    main()
