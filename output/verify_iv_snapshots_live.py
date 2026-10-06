"""Read-only TWS capture acceptance; retains provider evidence without account data."""
import contextlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import traceback

from dotenv import load_dotenv

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
load_dotenv(root / ".env")
os.environ["MOCK_DATA"] = "false"
os.environ["IB_CLIENT_ID"] = "87"
token = secrets.token_urlsafe(32)
os.environ["GAMMA_SESSION_TOKEN"] = token
directory = root / "output" / "iv-snapshots-live-2026-10-06"
directory.mkdir(parents=True, exist_ok=True)


def progress(message):
    print(message, flush=True)


def save(name, payload):
    (directory / name).write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")


summary = {"mock_mode": False, "symbol": "SPY", "captures": []}
try:
    with (directory / "runtime.log").open("w", encoding="utf-8") as logs:
        with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            from fastapi.testclient import TestClient
            from src.api.main import app, create_app
            from src.application.runtime import build_runtime
        with TestClient(app, headers={"X-Gamma-Session": token}) as client:
            with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
                status = client.post("/system/connection", json={"connected": True})
            status.raise_for_status()
            state = status.json()
            summary["connected"] = state["connection"]["connected"]
            assert not state["mock_mode"] and summary["connected"], "Live TWS connection unavailable"
            progress("Live TWS connected; acquiring SPY capture 1.")
            for index in range(2):
                if index:
                    time.sleep(10)
                    progress("Acquiring SPY capture 2.")
                with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
                    response = client.get("/iv/surface", params={"symbol": "SPY", "market_data_mode": "live",
                        "depth_preset": "compact", "surface_model": "linear", "wait_seconds": 30})
                response.raise_for_status()
                surface = response.json()
                save(f"surface-{index + 1}.json", surface)
                assert surface["snapshot_available"] and surface["points"] > 0, "Live surface unavailable"
                assert surface["source_provider"] == "ibkr", "Expected IBKR provider"
                retained = client.post("/iv/snapshots", json=surface)
                retained.raise_for_status()
                capture = retained.json()
                assert capture["surface"] == surface, "Capture changed the displayed provider evidence"
                save(f"capture-{index + 1}.json", capture)
                summary["captures"].append({"snapshot_id": capture["snapshot_id"], "timestamp": surface["timestamp"],
                    "captured_at": capture["captured_at"], "source_provider": surface["source_provider"],
                    "freshness_label": surface["freshness_label"], "delayed": surface["delayed"],
                    "spot": surface["spot"], "points": surface["points"], "quality": surface["quality"],
                    "warnings": surface["warnings"], "exact_payload_preserved": True})
                progress(f"Capture {index + 1} saved: {surface['points']} points, {surface['freshness_label']}, delayed={surface['delayed']}.")
        progress("Original runtime stopped; reading both captures through a fresh runtime.")
        with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            restarted = build_runtime(mock_mode=False)
        try:
            with TestClient(create_app(restarted, session_token=token), headers={"X-Gamma-Session": token}) as client:
                listing = client.get("/iv/snapshots?symbol=SPY")
                listing.raise_for_status()
                saved_ids = {item["snapshot_id"] for item in listing.json()["snapshots"]}
                for index, capture in enumerate(summary["captures"]):
                    assert capture["snapshot_id"] in saved_ids
                    response = client.get(f"/iv/snapshots/{capture['snapshot_id']}")
                    response.raise_for_status()
                    assert response.json() == json.loads((directory / f"capture-{index + 1}.json").read_text()), "Restart changed retained evidence"
                summary["restart_exact_replay"] = True
                summary["storage_warnings"] = listing.json()["warnings"]
        finally:
            with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
                restarted.shutdown()
        summary["status"] = "passed"
except Exception as error:
    summary["status"] = "failed"
    summary["error"] = str(error)
    (directory / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
finally:
    save("summary.json", summary)
    progress(json.dumps(summary, allow_nan=False))
