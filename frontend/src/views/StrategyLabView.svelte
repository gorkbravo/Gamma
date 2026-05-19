<script lang="ts">
  import ResearchView from "./ResearchView.svelte";
  import type {
    ResearchCompareResult,
    ResearchOverviewResponse,
    ResearchResult,
    SavedResearchItem,
    StrategyLabCompositionResult,
    StrategyLabResult
  } from "../lib/api/types";
  import type {
    ResearchCompareOptions,
    ResearchOverviewLoadOptions,
    ResearchRunOptions,
    SavedResearchCreateOptions,
    StrategyLabAnalyzeOptions,
    StrategyLabComposeOptions
  } from "../lib/stores/app";
  import type { StrategyLabMode } from "../lib/view-models/research";

  export let mode: StrategyLabMode = "composer";
  export let overview: ResearchOverviewResponse | null = null;
  export let result: ResearchResult | null = null;
  export let strategyResult: StrategyLabResult | null = null;
  export let strategyComposition: StrategyLabCompositionResult | null = null;
  export let compareResult: ResearchCompareResult | null = null;
  export let savedItems: SavedResearchItem[] = [];
  export let loading = false;
  export let overviewLoading = false;
  export let strategyLoading = false;
  export let compareLoading = false;
  export let savedLoading = false;
  export let selectedEquitySymbol: string | null = null;
  export let onLoadOverview: (options?: ResearchOverviewLoadOptions) => Promise<unknown> | void;
  export let onRun: (options: ResearchRunOptions) => void;
  export let onSelectEquity: ((symbol: string, label?: string | null) => void) | undefined = undefined;
  export let onAnalyzeStrategy: (options: StrategyLabAnalyzeOptions) => Promise<StrategyLabResult | null> | void;
  export let onComposeStrategy: (options: StrategyLabComposeOptions) => Promise<StrategyLabCompositionResult | null> | void;
  export let onCompare: (options: ResearchCompareOptions) => Promise<ResearchCompareResult | null> | void;
  export let onLoadSaved: () => Promise<SavedResearchItem[]> | void;
  export let onSaveResearch: (options: SavedResearchCreateOptions) => Promise<SavedResearchItem | null> | void;
  export let onDeleteSaved: (itemId: string) => Promise<boolean> | void;
  export let onRestoreStrategy: ((result: StrategyLabResult) => void) | undefined = undefined;
  export let onOpenRisk: (() => void) | undefined = undefined;
  export let onOpenIv: (() => void) | undefined = undefined;
</script>

<ResearchView
  surface="strategy"
  bind:mode
  {overview}
  {result}
  {strategyResult}
  {strategyComposition}
  {compareResult}
  {savedItems}
  {loading}
  {overviewLoading}
  {strategyLoading}
  {compareLoading}
  {savedLoading}
  {selectedEquitySymbol}
  {onLoadOverview}
  {onRun}
  {onSelectEquity}
  {onAnalyzeStrategy}
  {onComposeStrategy}
  {onCompare}
  {onLoadSaved}
  {onSaveResearch}
  {onDeleteSaved}
  {onRestoreStrategy}
  {onOpenRisk}
  {onOpenIv}
/>
