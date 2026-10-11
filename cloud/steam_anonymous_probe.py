"""Read-only anonymous WARDOGS Steam lobby probe on an ephemeral GitHub Actions runner.
No cookies, authentication, Discord calls, or private Steam session files.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

APP_ID = '1867240'
PROFILES = [
    ('D4rkN1ght', '76561198017193470'),
    ('Wrexcore', '76561199685613122'),
    ('Arclite', '76561198015564651'),
    ('Cody', '76561198289471656'),
    ('JayPee', '76561198022866377'),
    ('Nanox', '76561199219250693'),
    ('Guenther', '76561198016087360'),
    ('Nastily', '76561198120389931'),
]
JOIN = re.compile(r'^steam://joinlobby/1867240/(\d{10,25})/(7656119\d{10})$', re.I)
OUTPUT = Path('steam_anonymous_probe_result.json')


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    result = {'started_at':utc(), 'method':'GitHub Actions anonymous Playwright Chromium (no login)',
              'app_id':APP_ID, 'results':[], 'disclaimer':'Not detected does not mean offline. No Discord changes.'}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-first-run', '--disable-extensions'])
            try:
                context = browser.new_context(locale='de-DE', viewport={'width':1360,'height':900}, accept_downloads=False)
                page = context.new_page()
                for index, (name, sid) in enumerate(PROFILES, 1):
                    row={'friend':name, 'steam_id':sid, 'http_status':None, 'wardogs_visible':False,
                         'join_link_found':False, 'lobby_id':None, 'status':'not_detected'}
                    try:
                        response=page.goto('https://steamcommunity.com/profiles/'+sid+'/',
                                           wait_until='domcontentloaded', timeout=45000)
                        row['http_status']=response.status if response else None
                        if row['http_status'] != 200:
                            row['status']='http_error'
                        else:
                            page.wait_for_timeout(3000)
                            try:
                                page.locator('a[href^="steam://joinlobby/"]').first.wait_for(state='attached',timeout=4000)
                            except PWTimeout:
                                pass
                            row['wardogs_visible']='WARDOGS' in page.locator('body').inner_text(timeout=15000).upper()
                            hrefs=page.locator('a[href^="steam://joinlobby/"]').evaluate_all(
                                '(nodes) => nodes.map(n => n.getAttribute("href") || "")')
                            matches=[JOIN.fullmatch(h) for h in hrefs]
                            matches=[m for m in matches if m and m.group(2)==sid]
                            if matches:
                                row['join_link_found']=True
                                row['lobby_id']=matches[0].group(1)
                                row['status']='found'
                    except Exception as exc:
                        row['status']='error'
                        row['error_type']=type(exc).__name__
                    result['results'].append(row)
                    print(f'{index}/{len(PROFILES)} {name}: {row["status"]}; HTTP={row["http_status"]}; WARDOGS visible={row["wardogs_visible"]}; join link={row["join_link_found"]}',flush=True)
                    if row['http_status']==429:
                        print('Steam rate-limited the runner; stopping to avoid further requests.',flush=True)
                        break
                    if index < len(PROFILES):
                        page.wait_for_timeout(4000)
            finally:
                browser.close()
    except Exception as exc:
        result['fatal_error']=f'{type(exc).__name__}: {str(exc)[:200]}'
    result['finished_at']=utc()
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows=result['results']
    hits=sum(r['join_link_found'] for r in rows)
    ok=sum(r['http_status']==200 for r in rows)
    print(f'RESULT: {ok}/{len(rows)} HTTP 200; {hits} valid joinlobby links; {len(rows)}/{len(PROFILES)} checked.')
    if hits==0:
        print('INCONCLUSIVE: anonymous Steam cannot reliably expose friends-only lobby links. This is not proof players are offline.')
    if result.get('fatal_error') or len(rows)!=len(PROFILES) or ok!=len(PROFILES):
        print('WARNING: incomplete scan or network/rate-limit failure. No data was published to Discord.')
        return 1
    return 0

if __name__=='__main__':
    sys.exit(main())
