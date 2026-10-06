"""Real-browser commodity curve capture acceptance with a real server restart; read-only TWS optional."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

if "--serve" in sys.argv:
    import uvicorn
    from src.api.main import create_app
    from src.application.runtime import build_runtime
    directory = Path(os.environ["GAMMA_CURVES_EVIDENCE"])
    runtime = build_runtime(mock_mode=os.environ["GAMMA_CURVES_LIVE"] != "1",
                            history_dir=Path(os.environ["GAMMA_CURVES_RUN_DATA"]) / "data", cache_dir=Path(os.environ["GAMMA_CURVES_RUN_DATA"]) / "cache")
    uvicorn.run(create_app(runtime, session_token=os.environ["GAMMA_SESSION_TOKEN"]), host="127.0.0.1", port=8015)
    sys.exit(0)

import httpx

live = "--live" in sys.argv
directory = ROOT / "output" / "playwright" / ("commodity-curves-live" if live else "commodity-curves-mock")
directory.mkdir(parents=True, exist_ok=True)
token = secrets.token_urlsafe(32)
environment = dict(os.environ, GAMMA_CURVES_API="http://127.0.0.1:8015", GAMMA_CURVES_TOKEN=token,
                   GAMMA_SESSION_TOKEN=token, GAMMA_CURVES_LIVE="1" if live else "0",
                   GAMMA_CURVES_EVIDENCE=str(directory), GAMMA_CURVES_RUN_DATA=str(directory / "runs" / str(time.time_ns())), MOCK_DATA="false" if live else "true", IB_CLIENT_ID="89",
                   RESEARCH_MARKET_DATA_PROVIDERS="ibkr",
                   COMMODITIES_PROVIDER="ibkr" if live else "sample", IBKR_COMMODITIES_ENABLED="wti",
                   IBKR_COMMODITIES_STARTUP_ENABLED="wti", IBKR_COMMODITIES_BREADTH_ENABLED="none",
                   IBKR_COMMODITIES_CONTRACT_DEPTH="6", IBKR_COMMODITIES_HISTORY_DAYS="0",
                   EIA_API_KEY="", FRED_API_KEY="")
summary = {"live": live, "status": "failed", "server_restart": False}
server = None


def stop():
    global server
    if server:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        server = None


try:
    for phase in ("capture", "replay"):
        with (directory / f"server-{phase}.log").open("w", encoding="utf-8") as logs:
            server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve"], env=environment,
                                      stdout=logs, stderr=logs, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            with httpx.Client(base_url=environment["GAMMA_CURVES_API"], headers={"X-Gamma-Session": token}, timeout=90) as client:
                started = False
                for _ in range(120):
                    try:
                        response = client.get("/system/status")
                        if response.status_code == 200:
                            started = True
                            break
                    except httpx.ConnectError:
                        pass
                    if server.poll() is not None:
                        raise RuntimeError("Acceptance server stopped; inspect server log")
                    time.sleep(0.5)
                assert started, "Acceptance server did not start"
                if live and phase == "capture":
                    response = client.post("/system/connection", json={"connected": True})
                    response.raise_for_status()
                    state = response.json()
                    assert state["connection"]["connected"] and not state["mock_mode"]
                    print("Live TWS connected. Browser capturing WTI curves.", flush=True)
                elif phase == "replay":
                    summary["server_restart"] = True
                    # Deliberately leave TWS disconnected: reopening must use retained data.
                    print("Fresh server started. Browser reopening curves, comparing contracts and replaying the saved calendar spread.", flush=True)
                else:
                    print("Mock server ready. Browser capturing WTI curves.", flush=True)
            result = subprocess.run(["npx.cmd" if os.name == "nt" else "npx", "playwright", "test", "e2e/commodity-curves.spec.ts", "--workers=1"],
                                    cwd=ROOT / "frontend", env=dict(environment, GAMMA_CURVES_PHASE=phase),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            (directory / f"browser-{phase}.txt").write_text(result.stdout, encoding="utf-8")
            print(result.stdout[-6000:], flush=True)
            assert result.returncode == 0, f"Browser {phase} failed"
            stop()
    evidence = json.loads((directory / "capture.json").read_text())
    replay = json.loads((directory / "replay.json").read_text())
    assert replay["comparison"]["baseline"] == evidence["captures"][0]
    assert replay["comparison"]["comparison"] == evidence["captures"][1]
    summary.update(status="passed", capture_ids=[c["id"] for c in evidence["captures"]],
                   spread_id=evidence["spread"]["id"], contracts=len(evidence["captures"][0]["payload"]["curve"]["nodes"]),
                   providers=sorted({n["source_provider"] for c in evidence["captures"] for n in c["payload"]["curve"]["nodes"]}),
                   exact_capture_replay=True, spread_observations=len(replay["history"]["points"]))
except Exception as error:
    summary["error"] = str(error)
finally:
    stop()
    (directory / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
if summary["status"] != "passed":
    sys.exit(1)
