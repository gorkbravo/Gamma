# Phase 5 Agent Prompt

Use this prompt with another coding agent working inside the Gamma repo.

```text
You are working in the Gamma repository at the current roadmap stage after Phase 4 has reached an intermediate but usable foundation.

Start by reading these files before making decisions:
- roadmap.md
- README.md
- docs/README.md

Context and product boundary:
- Gamma is a read-only research environment, not a trading bot and not an execution platform.
- Preserve the roadmap's data-first architecture bias.
- Favor provider adapters, normalized schemas, reusable analytics, cache/storage hooks, provenance, and research workflows over shallow UI-only additions.
- Do not turn Gamma into a crypto trading terminal.
- Phase 5 is the active push target.
- The default goal is to one-shot as much of Phase 5 as the repo can realistically support in a single pass.
- Do not assume you should stop at a narrow slice.
- First try to land the full phase or the broadest end-to-end implementation that can be made coherent and shippable.
- Only if a true one-shot is not realistic should you fall back to a smaller but still materially useful subset.
- If you fall back, stop at a reasonable depth with a real shipped vertical slice, not scaffolding.

Current app shape:
- Backend: FastAPI in src/api, application logic in src/application, services/adapters in src/services, models in src/models.
- Frontend: Svelte in frontend/src.
- Existing research tabs already include Macro and Prediction Markets.
- Phase 4 Copilot exists and is in progress, so any new Phase 5 work should preserve or extend Copilot compatibility rather than bypass it.

Primary goal:
Materially advance Phase 5 - Crypto in a roadmap-aligned way. Deliver the deepest coherent vertical slice you can, not scattered partial stubs.

Execution mindset:
- Aim for the strongest plausible one-pass delivery, not the safest minimal increment.
- Prefer completing multiple connected Phase 5 surfaces in one integrated implementation if the architecture supports it.
- Treat a partial slice as the fallback path, not the default plan.
- Keep ambition high, but do not fake completeness with placeholder code.

Phase 5 target from the roadmap:
- Token explorer
- Narrative and sector baskets
- Wallet and flow analytics
- DEX / liquidity view
- Cross-sectional screening
- Comparative analytics
- Optional derivatives overlays are explicitly later, not required for v1

Implementation strategy:
1. Read the existing codebase and map the best insertion points for a new `Crypto` research tab.
2. Reuse existing Gamma patterns where possible:
   - route layer in src/api/routes
   - schema layer in src/api/schemas
   - application service layer in src/application
   - provider adapters in src/services
   - domain models in src/models
   - frontend store wiring in frontend/src/lib/stores/app.ts
   - new Svelte view/components under frontend/src/views and frontend/src/components
3. Keep Phase 5 scoped to a coherent first pass. Prefer one strong end-to-end slice over broad but shallow scaffolding.

Preferred delivery order:
1. Add the top-level `Crypto` tab to the research workspace only if the current navigation architecture supports it cleanly.
2. Implement a first-pass backend domain model and adapter boundary for crypto data.
3. Ship at least one usable end-to-end research surface:
   - best case: token explorer + screener + first-pass narrative grouping
   - next best: token explorer + screener
4. Add provenance metadata consistently to returned entities.
5. If practical, add first-pass Copilot context support for the new crypto domain using the existing Phase 4 patterns.
6. Add tests for backend and any critical frontend normalization/store behavior.
7. Update README if the product surface materially changes.

Important planning rule:
- Before coding, decide whether a credible one-shot of most of Phase 5 is possible.
- If yes, pursue that broader implementation.
- If no, choose the deepest coherent subset you can actually finish and verify.
- Do not prematurely retreat to the smallest possible scope.

Data-source guidance:
- Start with broad, accessible public crypto market coverage first.
- The roadmap suggests CoinGecko for broad token coverage and GeckoTerminal / CoinGecko on-chain coverage for DEX and pool context.
- Wallet/deeper on-chain analytics through Alchemy or Dune are desirable but should not block a usable first-pass vertical slice.
- If live data is impractical in one pass, support mock/sample-first development cleanly without violating the architecture.

Strongly preferred first-pass deliverable:
- `Crypto` tab with:
  - token search / selection
  - token profile/overview
  - price history
  - market cap / FDV / circulating supply / volume context where available
  - category/narrative tags
  - a basic screener for filtering/sorting a token universe
  - provenance-rich API responses

Good additional stretch work if time allows:
- narrative/sector basket summaries
- DEX liquidity/pool context
- comparative token vs token or token vs basket view
- Copilot domain integration for crypto using the same structured research-card pattern as existing tabs

Explicit non-goals for this pass unless the codebase already makes them cheap:
- trading or execution features
- wallet write actions
- full derivatives terminal
- overbuilt portfolio integrations that dilute the read-only research boundary
- AI-only crypto UI without underlying data architecture

Quality bar:
- Follow existing Gamma naming and architectural conventions.
- Keep routes thin.
- Put transformation logic in services/application, not in Svelte components.
- Add or preserve source/provider, retrieval timestamp, origin, and transformation note metadata where important.
- Avoid speculative abstractions unless they clearly support later roadmap work.
- If you add heuristics, label them as Gamma-defined heuristics.

Testing bar:
- Add focused tests for the new backend service/route behavior.
- Add frontend tests for any non-trivial normalization or rendering logic you introduce.
- Run the relevant targeted tests you add.
- If something cannot be tested, state exactly what remains unverified.

Copilot integration guidance:
- If you add Crypto context support, do it in the same style as the existing Copilot implementation:
  - read-only context bundle
  - tool-backed summaries/drilldowns if useful
  - provenance-aware structured research card outputs
- Do not let Copilot work block the core Crypto data slice if time is tight.

Decision rule:
- Try to one-shot the phase first.
- If the full phase is not realistically finishable in one pass, then and only then reduce scope.
- When reducing scope, preserve ambition: deliver the deepest roadmap-aligned working subset you can, wired through backend, frontend, and tests.
- Never stop at scaffolding, placeholders, or architecture-only prep unless the repo blocks further progress.

Before finishing:
- Summarize what part of Phase 5 is now actually implemented.
- Call out what remains open.
- State whether the new work is enough to consider Phase 5 "started" in a meaningful way.
```
