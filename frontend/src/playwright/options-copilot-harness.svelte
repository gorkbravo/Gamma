<script lang="ts">
  import IvView from "../views/IvView.svelte";
  import CopilotView from "../views/CopilotView.svelte";
  import type { CopilotWorkingAnalysis, IvSurface, IvOptionPair } from "../lib/api/types";
  import type { OptionsMode } from "../lib/view-models/iv";
  import { activeCopilotSession, copilotThreads, executeCopilotOperatorPlan, ivSurface,
    loadActiveCopilotSession, retryCopilotTurn, streamCopilotResearchCard } from "../lib/stores/app";

  localStorage.setItem("gamma.copilot.session", "options-continuity");
  let mounted = true;
  let mode: OptionsMode = "strategies";
  const surfaceContext = { supported: true, domain: "iv" as const, contextLabel: "GOOGL Options",
    domainLabel: "Options", guidance: "Evaluate the selected strategy.", placeholder: "Evaluate this spread",
    selectedScopeDomains: ["iv" as const], selectionMessage: "Options selected", scopeOptions: [], thread: null };

  function makeSurface(symbol: string): IvSurface {
    const strikes = symbol === "GOOGL" ? [315, 330, 340, 350] : [210, 225, 235, 245];
    const expiries = ["20261120", "20270115"];
    return { symbol, timestamp: "2026-10-04T12:00:00Z", retrieved_at: "2026-10-04T12:00:00Z",
      snapshot_available: true, spot: symbol === "GOOGL" ? 337.76 : 233,
      expiries, strikes, iv_grid: expiries.map(() => strikes.map(() => 0.33)), delayed: true,
      points: 8, warnings: [], messages: [], source_provider: "mock", origin: "playwright.options",
      transformation_note: null, freshness_label: "mocked", collection: null, quality: null,
      pairs: expiries.flatMap((expiry) => strikes.map((strike, index) => ({
        pair_id: `${symbol}:${expiry}:${strike}`, expiry, strike, days_to_expiry: 47,
        call_price: 20 - index * 3, put_price: 5 + index * 4,
        call_implied_volatility: 0.33, put_implied_volatility: 0.33, blended_implied_volatility: 0.33,
      } as IvOptionPair))) };
  }
  let result = makeSurface("GOOGL");
  ivSurface.set(result);
  const workingAnalysis = new URLSearchParams(location.search).has("temporary") ? {
    analysis_id: "temporary-option-set", session_id: "options-continuity", run_id: null,
    status: "active", state_scope: "session_ephemeral", analysis_type: "options_strategy_draft",
    owning_tab: "iv", owning_mode: "strategies", entity: { symbol: "GOOGL" }, inputs: {},
    outputs: { contracts: 1, legs: [{ side: "long", option_type: "put", expiry: "20261120", strike: 340, premium: 13, quantity: 1 }] },
    materialization: { durable: false, payload_contract: "copilot.options-strategy-working-analysis.v1" },
    source_ids: [], warnings: [], source_provider: "mock", created_at: "2026-10-04T12:00:00Z",
    expires_at: "2026-10-11T12:00:00Z",
  } as CopilotWorkingAnalysis : null;
  function changeSymbol() { result = makeSurface("AAPL"); ivSurface.set(result); }
  function updateBackgroundSurface() { ivSurface.set(makeSurface("AAPL")); }
  async function generate(domain: "iv", prompt = "") {
    await streamCopilotResearchCard(domain, prompt, { workspaceMode: "research" });
    await loadActiveCopilotSession();
  }
  async function runOperator(domain: "iv", prompt = "") {
    await executeCopilotOperatorPlan(domain, prompt, { workspaceMode: "research" });
  }
</script>

<button type="button" on:click={() => (mounted = !mounted)}>{mounted ? "Leave Options" : "Return to Options"}</button>
<button type="button" on:click={changeSymbol}>Load AAPL</button>
<button type="button" on:click={updateBackgroundSurface}>Background surface update</button>
{#if mounted}
  <IvView bind:mode {result} {workingAnalysis} requestedSymbol={result.symbol} onLoad={() => {}} onStopSession={() => {}}
    onSendToCopilot={() => (mounted = false)} />
{:else}
  <CopilotView surface={surfaceContext} synthesisSurface={surfaceContext} activeSession={$activeCopilotSession}
    thread={$copilotThreads.iv} onGenerate={generate} onRunOperator={runOperator} onRetryTurn={retryCopilotTurn} />
{/if}
