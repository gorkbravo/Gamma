"""Servidor local determinista para la verificación en navegador de E4 (libro de pesos) y E5 (parámetros,
barridos, walk-forward). Nunca usa proveedores configurados ni ejecuta Python: el runtime de fixture deriva
gamma_analytics.json de los parámetros recibidos. Validación, libro, comparación y walk-forward son reales.
"""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from script_e5_fixtures import e5_service
from src.api.routes.research import router
from src.models.research_script import ResearchScriptInputBundleRequest, ResearchScriptInputFileCreateRequest

PORT = 8775


def main():
    with TemporaryDirectory(prefix="gamma-e5-browser-") as directory:
        service, detail = e5_service(Path(directory))
        # Un paquete explícito (aunque el fixture no lo lea) para que el barrido ligue unas entradas exactas.
        service.create_input_bundle(detail.script.script_id, ResearchScriptInputBundleRequest(input_files=[
            ResearchScriptInputFileCreateRequest(logical_filename="notes.txt", media_type="text/plain",
                                                 content=b"E5 browser fixture input; values are derived from parameters.")]))
        app = FastAPI()
        app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://127.0.0.1:5174"],
                           allow_methods=["*"], allow_headers=["*"])
        app.state.runtime = SimpleNamespace(research_script_service=service, research_service=service.research_service)
        app.include_router(router)
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
