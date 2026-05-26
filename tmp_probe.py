import json, os, sys
fn = sys.argv[1]
d = json.load(open(os.environ['TEMP'] + f'/{fn}.json'))
print('=== COMPANY ===')
print(json.dumps(d.get('company', {}), default=str, indent=1)[:400])
print()
print('=== HEADLINE ===')
for m in d.get('headline_metrics', []):
    print(f"  {m.get('label'):24} {m.get('display_value')}")
print()
print('=== DCF SUMMARY ===')
for s in d.get('dcf_summary', []):
    ipv = s.get('implied_value_per_share')
    low = s.get('implied_value_low')
    high = s.get('implied_value_high')
    cur = s.get('current_price')
    up = s.get('upside_downside_pct')
    def f(x):
        return f"{x:.2f}" if isinstance(x, (int, float)) else str(x)
    print(f"  {s.get('label'):6} implied=${f(ipv)} (low ${f(low)} / high ${f(high)}) | current=${cur} | upside={up}")
print()
print('=== PRICE HISTORY (last 5) ===')
ph = d.get('price_history') or []
if isinstance(ph, dict):
    ph = ph.get('points') or ph.get('history') or []
for p in ph[-5:]:
    print(' -', p.get('timestamp') or p.get('date'), p.get('close') or p.get('price'))
print()
print('=== WARNINGS ===')
for w in d.get('warnings', []):
    print(' -', w[:200])
print()
print('=== PEER CANDIDATES ===')
for p in (d.get('peer_candidates') or [])[:8]:
    print(' -', p.get('ticker'), '|', p.get('name'))
print()
print('=== PEER BASKET ===')
pb = d.get('peer_basket') or {}
print(' peer_tickers:', pb.get('peer_tickers'))
