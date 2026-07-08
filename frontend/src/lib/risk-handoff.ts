import type { ResearchResult, TabId } from "./api/types";
import type { RiskComputeOptions, StrategyLabResearchBook } from "./stores/app";
import { buildRiskRequestFromResearch } from "./workspace";

export type RiskHandoffController = {
  readonly running: boolean;
  open: () => Promise<unknown>;
};

export function buildStrategyLabRiskRequest(book: StrategyLabResearchBook): RiskComputeOptions {
  return {
    snapshot: book.snapshot,
    sourceScope: "research_book",
    researchBookReturnPoints: book.object.return_points,
    riskSourceLabel: book.sourceLabel,
    riskSourceObjectId: book.object.object_id,
    riskSourceOrigin: String(book.object.provenance.origin ?? "strategy_lab"),
    alpha: 0.95,
    lookbackDays: 252,
    horizonDays: 1,
    mcHorizonDays: 10,
    mcSimulationModel: "Gaussian",
    mcNumSimulations: 2000,
    betaWindow: 126,
    benchmarkSymbol: book.benchmarkSymbol || "SPY"
  };
}

export function createRiskHandoffController(deps: {
  getActiveTab: () => TabId;
  getStrategyLabResearchBook: () => StrategyLabResearchBook | null;
  getResearchResult: () => ResearchResult | null;
  setActiveTab: (tab: TabId) => void;
  computeRisk: (options: RiskComputeOptions) => Promise<unknown> | unknown;
  onRunningChange?: (running: boolean) => void;
  onError?: (error: unknown) => void;
}): RiskHandoffController {
  let runningPromise: Promise<unknown> | null = null;

  return {
    get running() {
      return runningPromise != null;
    },
    open() {
      if (runningPromise) {
        return runningPromise;
      }
      runningPromise = (async () => {
        deps.onRunningChange?.(true);
        try {
          if (deps.getActiveTab() === "strategy_lab") {
            const book = deps.getStrategyLabResearchBook();
            if (book) {
              deps.setActiveTab("risk");
              return await deps.computeRisk(buildStrategyLabRiskRequest(book));
            }
          }
          const request = buildRiskRequestFromResearch(deps.getResearchResult());
          if (!request) {
            return null;
          }
          deps.setActiveTab("risk");
          return await deps.computeRisk(request);
        } catch (error) {
          deps.onError?.(error);
          return null;
        } finally {
          runningPromise = null;
          deps.onRunningChange?.(false);
        }
      })();
      return runningPromise;
    }
  };
}
