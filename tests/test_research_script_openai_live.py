from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.application.research_script_service import ResearchScriptService
from src.models.research_script import (
    ResearchScriptCreateRequest,
    ResearchScriptInputFileCreateRequest,
    ResearchScriptRunCreateRequest,
)
from src.services.openai_research_script_runtime import OpenAICodeInterpreterRuntime
from src.services.research_script_runtime import MockResearchScriptRuntime
from src.services.research_script_store import ResearchScriptStore


SPY_MONTHLY = b"""date,close
2025-01-31,100
2025-02-28,103
2025-03-31,101
2025-04-30,106
2025-05-31,109
2025-06-30,108
2025-07-31,112
2025-08-31,116
2025-09-30,114
2025-10-31,119
2025-11-30,123
2025-12-31,126
2026-01-31,124
2026-02-28,129
2026-03-31,133
2026-04-30,131
2026-05-31,136
2026-06-30,140
2026-07-31,143
2026-08-29,147
"""

MOVING_AVERAGE_SOURCE = '''import csv
import json

with open("prices.csv", newline="", encoding="utf-8") as handle:
    prices = list(csv.DictReader(handle))

closes = [float(row["close"]) for row in prices]
dates = [row["date"] for row in prices]
short_window = 3
long_window = 6
rows = []
strategy_value = 1.0
peak = 1.0
max_drawdown = 0.0

for index, close in enumerate(closes):
    short_ma = sum(closes[max(0, index - short_window + 1):index + 1]) / min(index + 1, short_window)
    long_ma = sum(closes[max(0, index - long_window + 1):index + 1]) / min(index + 1, long_window)
    invested = index >= long_window - 1 and short_ma > long_ma
    monthly_return = 0.0 if index == 0 else close / closes[index - 1] - 1.0
    strategy_return = monthly_return if invested else 0.0
    strategy_value *= 1.0 + strategy_return
    peak = max(peak, strategy_value)
    drawdown = strategy_value / peak - 1.0
    max_drawdown = min(max_drawdown, drawdown)
    rows.append({
        "date": dates[index],
        "close": f"{close:.2f}",
        "short_ma": f"{short_ma:.4f}",
        "long_ma": f"{long_ma:.4f}",
        "invested": str(invested).lower(),
        "cumulative_return": f"{strategy_value - 1.0:.6f}",
        "drawdown": f"{drawdown:.6f}",
    })

with open("cumulative_returns.csv", "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

width, height, margin = 720, 280, 30
values = [float(row["cumulative_return"]) for row in rows]
low, high = min(values), max(values)
span = max(high - low, 1e-9)
points = []
for index, value in enumerate(values):
    x = margin + index * (width - margin * 2) / max(len(values) - 1, 1)
    y = height - margin - (value - low) * (height - margin * 2) / span
    points.append(f"{x:.1f},{y:.1f}")
svg = (
    f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    '<rect width="100%" height="100%" fill="#070809"/>'
    '<text x="30" y="22" fill="#c2c8d0" font-family="monospace" font-size="13">SPY monthly MA crossover</text>'
    f'<polyline fill="none" stroke="#7aa6c8" stroke-width="3" points="{" ".join(points)}"/>'
    '</svg>'
)
with open("crossover_chart.svg", "w", encoding="utf-8") as handle:
    handle.write(svg)
with open("run_summary.json", "w", encoding="utf-8") as handle:
    json.dump({
        "ticker": "SPY",
        "frequency": "monthly",
        "short_window": short_window,
        "long_window": long_window,
        "max_drawdown": max_drawdown,
        "warnings": ["Deterministic Gamma snapshot; no live market data or transaction costs."],
    }, handle, indent=2)

print(f"SPY crossover complete; max drawdown={max_drawdown:.6f}")
print("WARNING: deterministic Gamma snapshot; no live market data or transaction costs.")
'''


@pytest.mark.skipif(
    os.getenv("GAMMA_RUN_LIVE_RESEARCH_SCRIPT_SMOKE", "").strip().lower()
    not in {"1", "true", "yes", "on"},
    reason="Live Research Script smoke is explicitly opt-in.",
)
def test_live_openai_code_interpreter_spy_acceptance(tmp_path: Path) -> None:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = (
        os.getenv("GAMMA_RESEARCH_SCRIPT_MODEL")
        or os.getenv("GAMMA_COPILOT_MODEL")
        or ""
    ).strip()
    if not api_key or not model:
        pytest.skip("Provider key and configured Gamma model are required.")
    runtime = OpenAICodeInterpreterRuntime(api_key=api_key, model=model)
    capabilities = runtime.capabilities()
    if not capabilities.available:
        pytest.skip(capabilities.sanitized_provider_status)

    base_dir = tmp_path / "live-research-script"
    service = ResearchScriptService(ResearchScriptStore(base_dir), runtime)
    detail = service.create_script(
        ResearchScriptCreateRequest(
            session_id="live-acceptance",
            title="SPY monthly moving-average crossover",
            source=MOVING_AVERAGE_SOURCE,
        )
    )
    revision = detail.revisions[0]
    run = service.create_run(
        detail.script.script_id,
        ResearchScriptRunCreateRequest(
            revision_id=revision.revision_id,
            input_files=[
                ResearchScriptInputFileCreateRequest(
                    logical_filename="prices.csv",
                    media_type="text/csv",
                    content=SPY_MONTHLY,
                    gamma_object_id="gamma-spy-monthly-2025-01-2026-08",
                    provider_id="gamma_historical_prices",
                    transformation_note="Copied monthly adjusted-close snapshot for deterministic acceptance.",
                    source_kind="gamma_state",
                )
            ],
            dataset_refs=[
                {
                    "dataset_id": "gamma-spy-monthly-2025-01-2026-08",
                    "provider": "gamma_historical_prices",
                    "ticker": "SPY",
                    "frequency": "monthly",
                    "coverage_start": "2025-01-31",
                    "coverage_end": "2026-08-29",
                }
            ],
            source_refs=[
                {
                    "source_id": "gamma-spy-monthly-acceptance",
                    "provider": "gamma_historical_prices",
                    "coverage": "2025-01-31/2026-08-29",
                }
            ],
        ),
    )

    assert run.status == "completed"
    assert run.source_sha256 == revision.source_sha256
    assert run.usage["executed_code"] is True
    assert run.usage["network_access"] is False
    assert run.provider_response_id and run.provider_container_id
    tables = [output for output in run.outputs if output.kind == "table"]
    images = [output for output in run.outputs if output.kind == "image"]
    assert tables and images, [
        (output.kind, output.filename, output.text) for output in run.outputs
    ]
    assert all(output.generated for output in [*tables, *images])
    assert any("drawdown" in output.columns for output in tables)
    assert any("transaction costs" in (output.text or "") for output in run.outputs)
    assert any("transaction costs" in warning for warning in run.warnings)

    restarted = ResearchScriptService(
        ResearchScriptStore(base_dir),
        MockResearchScriptRuntime(),
    )
    reopened = restarted.get_run(run.run_id)
    assert reopened.source_sha256 == revision.source_sha256
    for output in [tables[0], images[0]]:
        _, _, content = restarted.get_output_artifact(run.run_id, output.output_id)
        assert content
