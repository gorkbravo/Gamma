import json, os
d = json.load(open(os.environ['TEMP'] + '/news.json', encoding='utf-8'))
print('keys:', list(d.keys())[:15])
items = d.get('items') or d.get('news') or d.get('articles') or d.get('headlines') or d.get('news_items') or []
print('count:', len(items))
for it in items[:8] if isinstance(items, list) else []:
    print(' -', (it.get('title') or it.get('headline', '?'))[:100])
    print('   ', it.get('source'), '|', it.get('published_at') or it.get('timestamp'))
