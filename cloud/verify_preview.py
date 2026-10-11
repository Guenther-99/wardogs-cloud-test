"""Safe read-only preview validation; never contacts Discord."""
import json
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parent
config = json.loads((root / 'servers.json').read_text(encoding='utf-8'))
messages = json.loads((root / 'preview.json').read_text(encoding='utf-8'))
assert len(config['servers']) == 9, 'Expected 9 configured servers'
assert messages and all(isinstance(m.get('embeds'), list) for m in messages), 'Invalid preview embeds'
combined = json.dumps(messages, ensure_ascii=False)
for item in config['servers']:
    assert item['id'].lower() in combined, f"Missing server ID: {item['id']}"
    assert 'server.html?' in combined, 'Missing GitHub Pages links'
for message in messages:
    assert len(message['embeds']) <= 10, 'Too many embeds'
    assert len(message.get('content','')) <= 2000, 'Discord content too long'
    assert sum(len(e.get('title',''))+len(e.get('description','')) for e in message['embeds']) <= 6000, 'Discord embeds too large'
    for embed in message['embeds']:
        assert len(embed.get('description','')) <= 4096, 'Discord description too long'
assert not (root / 'webhook.json').exists(), 'Webhook config must not exist in cloud test'
assert not (root / 'state.json').exists(), 'Cloud test should not create persistent state'
assert not re.search(r'https://(?:discord(?:app)?\.com)/api/webhooks/\d+/', combined), 'Webhook URL leaked into output'
report = f'PASS: {len(config["servers"])} configured servers in {len(messages)} Discord preview message(s); no Discord writes or Steam authentication.'
print(report)
summary = pathlib.Path(__import__('os').environ.get('GITHUB_STEP_SUMMARY',''))
if str(summary) != '.':
    with summary.open('a',encoding='utf-8') as f:
        f.write('## WARDOGS V6 – echter Server-Cloud-Test\n\n')
        f.write(report + '\n\n')
        f.write('Es wurde nur eine Vorschau erzeugt. V5.1 bleibt unverändert.\n')
