<script lang="ts">
  import IvSnapshotComparison from "../components/IvSnapshotComparison.svelte";
  import type { IvSurface } from "../lib/api/types";
  let count = 0;
  function makeSurface(): IvSurface {
    return { symbol: "SPY", spot: 100, timestamp: `2026-10-06T${count ? "15" : "14"}:00:00Z`, retrieved_at: "2026-10-06T15:01:00Z",
      snapshot_available: true, points: 6, expiries: ["20261120", "20261218"], strikes: [95, 100, 105],
      iv_grid: [[0.3 + count * 0.04, 0.25 + count * 0.02, 0.26 + count * 0.01], [0.31, 0.27, 0.28]],
      cell_sources: [["observed", "observed", "observed"], ["observed", "observed", "observed"]],
      pairs: [], delayed: true, source_provider: "mock", freshness_label: "mocked", origin: "test",
      transformation_note: "Observed option-pair IV", warnings: ["Sample data"], messages: [], collection: null, quality: null,
      pricing_assumptions: { spot_reference: 100, risk_free_rate: 0.04, dividend_yield: 0.01, notes: ["Frozen assumptions"], fallback_greeks_methodology: "Black-Scholes" } };
  }
  let surface = makeSurface();
</script>
<main><button on:click={() => { count = 1; surface = makeSurface(); }}>Advance surface</button><IvSnapshotComparison {surface} symbol={surface.symbol} /></main>
<style>main { padding: var(--space-5); } main > button { margin-bottom: var(--space-4); }</style>
