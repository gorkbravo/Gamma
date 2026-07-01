# Agent Prompt: Workstream 9 - Maritime Intelligence

You are working in the Gamma repository. Your task is to start current-roadmap Workstream 9 and do as much useful implementation work as possible in the current session.

## First, Read The Correct Documentation

Before making code changes, read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `docs/README.md`
4. `roadmap.md`
5. `docs/provenance_expectations.md`

If you touch frontend UI, components, layouts, CSS, navigation, or browser-visible behavior, you must also read:

6. `docs/design_principles.md`

Do not skip the design principles for frontend work. Gamma has a strict dense, flat, read-only research UI style.

## Product Boundary

Gamma is a read-only market research environment. Maritime Intelligence must not become an execution, routing, alert-trading, or operational maritime platform.

The Workstream 9 goal is a credible maritime research surface that can inspect vessel movement, chokepoints, route changes, event windows, and commodity-flow links with clear source and coverage caveats.

The roadmap explicitly says live global coverage is blocked by AIS/provider evaluation. You may still make real progress by building stable internal contracts, mock or historical data paths, provider abstractions, backend services, tests, and an initial UI that honestly labels coverage as sample, historical, partial, or unavailable.

## Workstream 9 Scope

Build toward a Maritime Intelligence tab, not a generic AIS map.

It should eventually answer:

- Where are vessels clustering?
- Are chokepoints congested or disrupted?
- Are routes changing?
- Which commodity flows are affected?
- Are tankers, LNG carriers, bulkers, or container ships behaving differently?
- Is there a market or geopolitical event connected to this movement?
- Which signals should be handed to Commodities, Macro, or Copilot?

Suggested modes from `roadmap.md` Workstream 9:

- `Live Map`
- `Chokepoints`
- `Trade Flows`
- `Fleet / Vessel Monitoring`
- `Event Replay`
- `Risk Signals` later

Treat `Risk Signals` as later-stage unless the foundational model is already solid. Do not rush sanctions, shadow-fleet, dark-activity, or suspicious-behavior labels. If you add placeholders, include confidence and methodology caveats.

## Preferred Implementation Order

Do as much as possible, in this order. Stop only when blocked by time, missing dependencies, or unclear provider credentials.

1. Inspect existing backend/frontend patterns for tabs such as Macro, Crypto, Fundamentals, Prediction Markets, and provider capability metadata.
2. Define durable maritime domain models:
   - vessel identifiers such as MMSI and IMO
   - AIS position records
   - vessel static metadata
   - vessel type/class
   - ports and terminals
   - chokepoint definitions or polygons
   - route or track snippets
   - event windows
   - fleet/watchlist definitions
   - provider/freshness/coverage metadata
3. Add provider adapter boundaries before UI depth:
   - sample/mock provider first if live AIS is not available
   - optional historical dataset adapter if local sample data exists or can be cleanly added
   - clearly separated future live-provider interface for AISstream, AISHub, MarineCadastre, MarineTraffic, Spire, VesselFinder, or similar sources
4. Add backend application/service logic:
   - overview or workspace payload
   - vessel positions or sample tracks
   - chokepoint summaries
   - event replay payloads if feasible
   - coverage/freshness metadata
   - provenance on returned entities
5. Add API routes only after service contracts are coherent.
6. Add tests for schemas, service behavior, route behavior, and coverage/provenance caveats.
7. If time remains, add the frontend tab and modes using existing Gamma patterns.
8. If frontend work is done, wire it into app navigation and verify in the browser or desktop app.
9. Add Copilot or cross-domain hooks only if the core payload is stable enough to ground them honestly.

## Data And Provider Rules

Do not imply complete global AIS coverage unless a provider actually supports it.

Label all data with clear coverage language:

- `sample`
- `mock`
- `historical`
- `partial`
- `live`
- `unavailable`

Cargo inference must be explicit. AIS does not automatically identify cargo. If a flow is inferred from vessel type, route, port, or other proxy data, label it as inferred and include confidence or caveat text.

Potential providers from the roadmap:

- `AISstream` for prototype live AIS streaming
- `NOAA / MarineCadastre` for US historical AIS data
- `Global Fishing Watch` where terms fit
- `AISHub` if participation requirements are practical
- paid providers such as `MarineTraffic`, `Spire`, or `VesselFinder` if reliable global coverage is later needed
- user-owned shadow-fleet ML outputs in a later roadmap

Do not hard-code user secrets or provider keys. If a provider needs credentials, document the required environment variable and make the app degrade gracefully without it.

## UI Requirements If You Touch Frontend

Read `docs/design_principles.md` before frontend work.

Follow Gamma's existing design system:

- dense research surface
- no marketing-style landing page
- no decorative map/demo chrome
- no gradients, shadows, or filled cards on research panels
- use theme tokens from `frontend/src/lib/theme/tokens.css`
- preserve the flat plane model
- use a mode bar if the Maritime tab has multiple modes
- show coverage/freshness caveats where they affect interpretation
- use provenance selectively in UI, not as noisy developer text in every row

Start with a useful research workspace, not a visual-only map. A map is valuable, but the roadmap asks for interpretation: chokepoints, trade flows, event replay, coverage caveats, and cross-domain links.

## Objective Verification Requirement

Verify the work objectively, not just by inspection.

At minimum, run relevant automated checks:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

If frontend code changes:

```powershell
cd frontend
npm run test
npm run build
```

If you add or change app-visible behavior, try to verify it live in the app:

1. Start the backend in mock mode:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

2. Start the frontend:

```powershell
cd frontend
$env:VITE_API_BASE="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

3. Open the app in a browser or use Playwright/browser automation to confirm:
   - the app loads
   - the relevant workspace/tab is reachable
   - the Maritime UI, if implemented, renders without errors
   - sample/mock/historical coverage caveats are visible
   - mode switching and core controls work
   - API-backed data appears and failed providers degrade gracefully

If you cannot check the work live, say exactly why and what you need from the user. Examples:

- missing Node dependencies
- backend could not start
- port conflict
- no AIS provider key
- no local historical AIS dataset
- browser automation unavailable
- frontend route cannot be reached because navigation is not wired yet

Do not claim live verification if you only ran static tests.

## Expected Handoff

When you finish, provide a concise handoff with:

- what you implemented
- what files changed
- what tests/checks you ran and their results
- what you verified in the running app
- what could not be verified live and what is needed from the user
- remaining Workstream 9 next steps, ordered by dependency

Keep the work roadmap-aligned and preserve the read-only boundary throughout.
