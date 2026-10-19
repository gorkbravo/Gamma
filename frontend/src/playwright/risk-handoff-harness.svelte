<script lang="ts">
  import RiskView from "../views/RiskView.svelte";
  import type { PortfolioSnapshot, RiskResult } from "../lib/api/types";
  import type { RiskComputeOptions, StrategyLabResearchBook } from "../lib/stores/app";

  export let snapshot: PortfolioSnapshot | null;
  export let book: StrategyLabResearchBook;
  export let result: RiskResult;
  export let secondBook: StrategyLabResearchBook;
  export let secondResult: RiskResult;
  export let onCompute: (options: RiskComputeOptions) => void;

  // Simula un segundo traspaso de Strategy Lab con Risk ya montado y el libro seleccionado.
  function secondHandoff() {
    book = secondBook;
    result = secondResult;
  }
</script>

<button data-testid="second-handoff" on:click={secondHandoff}>Simulate Second Handoff</button>
<RiskView
  mode="portfolio"
  activeMode="overview"
  {snapshot}
  researchSnapshot={null}
  strategyLabResearchBook={book}
  {result}
  workingAnalysis={null}
  loading={false}
  {onCompute}
/>
