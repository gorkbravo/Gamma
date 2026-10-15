"""Local deterministic E4 browser fixture; never uses configured providers or Python execution."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from test_script_analytics import service_run, payload
from src.api.routes.research import router
from src.models.research_script import ResearchScriptCreateRequest, ResearchScriptRunCreateRequest


def main():
    with TemporaryDirectory(prefix="gamma-e4-browser-") as directory:
        service, _ = service_run(Path(directory), json.dumps(payload()).encode())
        for title, content, executed in [
            ("E4 invalid optional output", b'{"contract_version":"unknown"}', True),
            ("E4 safe preview", json.dumps(payload()).encode(), False),
            ("E4 valid fixture", json.dumps(payload()).encode(), True),
        ]:
            service.runtime.data = content
            service.runtime.executed = executed
            detail = service.create_script(ResearchScriptCreateRequest(session_id="e4-browser", title=title, source="print('Browser fixture; source is not executed')"))
            service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())
        app = FastAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
        app.state.runtime = SimpleNamespace(research_script_service=service, research_service=service.research_service)
        app.include_router(router)
        uvicorn.run(app, host="127.0.0.1", port=8774, log_level="warning")


if __name__ == "__main__":
    main()
