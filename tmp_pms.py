import json, urllib.request

def analyze(sym):
    req = urllib.request.Request(
        "http://127.0.0.1:8000/research/analyze",
        data=json.dumps({
            "scope_type": "single_ticker",
            "primary_symbol": sym,
            "benchmark_symbol": "SPY",
            "lookback_days": 252,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

for sym in ["PPLT", "GLD", "PALL", "SLV", "SBSW", "GDX", "GDXJ"]:
    try:
        d = analyze(sym)
        s = d.get("summary", {}) or {}
        def fp(x, w=6):
            return f"{x:>{w}.1%}" if isinstance(x, (int, float)) else f"{'N/A':>{w}}"
        def fb(x):
            return f"{x:>5.2f}" if isinstance(x, (int, float)) else f"{'N/A':>5}"
        print(f"  {sym:5} tot={fp(s.get('total_return'))} ann={fp(s.get('annual_return'))} vol={fp(s.get('annual_vol'),5)} dd={fp(s.get('max_drawdown'))} beta={fb(s.get('beta'))} corr={fb(s.get('correlation'))}")
    except Exception as e:
        print(f"  {sym:5} ERROR: {e}")
