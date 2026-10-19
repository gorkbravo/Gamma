import type { ResearchResult, TabId, TimeSeriesPoint } from "./api/types";
import type { RiskComputeOptions, StrategyLabResearchBook } from "./stores/app";
import { buildRiskRequestFromResearch } from "./workspace";

export type RiskHandoffController = {
  readonly running: boolean;
  open: () => Promise<unknown>;
};

export const NO_RETAINED_BENCHMARK_LABEL = "No retained benchmark";

export function strategyLabBookBenchmarkSymbol(book: StrategyLabResearchBook): string {
  return (book.benchmarkSymbol ?? "").trim().toUpperCase() || "SPY";
}

// El histórico retenido solo se reutiliza si Risk pide el mismo benchmark del experimento;
// otro símbolo elegido deliberadamente en Risk usa la ruta del proveedor (null).
export function strategyLabBenchmarkPoints(book: StrategyLabResearchBook, requestedSymbol: string): TimeSeriesPoint[] | null {
  const requested = requestedSymbol.trim().toUpperCase() || "SPY";
  return requested === strategyLabBookBenchmarkSymbol(book) ? book.composition?.benchmark_points ?? null : null;
}

// Un experimento sin histórico de benchmark retenido no debe etiquetarse con un símbolo que no se usó.
export function strategyLabBenchmarkLabel(book: StrategyLabResearchBook, requestedSymbol: string): string {
  const points = strategyLabBenchmarkPoints(book, requestedSymbol);
  return points && points.length === 0 ? NO_RETAINED_BENCHMARK_LABEL : requestedSymbol.trim().toUpperCase() || "SPY";
}

export interface StrategyLabBookControls {
  /** Identidad del libro cuyos parámetros siembran los controles de Risk. */
  key: string;
  benchmarkSymbol: string;
  lookbackDays: number | null;
}

// Un mismo experimento recompuesto conserva bookId pero cambia createdAt, y sus
// parámetros pueden ser otros; ambos forman la identidad que siembra los controles.
export function strategyLabBookControlsKey(book: StrategyLabResearchBook): string {
  return `${book.bookId}|${book.createdAt}`;
}

export function strategyLabBookControls(book: StrategyLabResearchBook): StrategyLabBookControls {
  return {
    key: strategyLabBookControlsKey(book),
    benchmarkSymbol: strategyLabBookBenchmarkSymbol(book),
    lookbackDays: book.composition?.portfolio_inputs?.lookback_days ?? null,
  };
}

/**
 * Controles que Risk debe adoptar del libro de Strategy Lab, o null si ya los
 * tiene. Se siembran por identidad del libro y no por cambio de fuente: un
 * segundo traspaso con el libro ya seleccionado, o una vista sin snapshot de
 * cuenta (donde el libro es la única fuente desde el montaje), dejaban el
 * benchmark y el lookback anteriores para el siguiente recálculo. Una edición
 * deliberada del usuario sobre el mismo libro no se sobrescribe.
 */
export function strategyLabControlsToSeed(input: {
  selected: string;
  book: StrategyLabResearchBook | null;
  seededKey: string | null;
}): StrategyLabBookControls | null {
  if (input.selected !== "strategy_lab_book" || !input.book) return null;
  const controls = strategyLabBookControls(input.book);
  return controls.key === input.seededKey ? null : controls;
}

export function buildStrategyLabRiskRequest(book: StrategyLabResearchBook): RiskComputeOptions {
  const benchmarkSymbol = strategyLabBookBenchmarkSymbol(book);
  return {
    snapshot: book.snapshot,
    sourceScope: "research_book",
    researchBookReturnPoints: book.object.return_points,
    researchBookBenchmarkPoints: strategyLabBenchmarkPoints(book, benchmarkSymbol),
    researchBookRiskLegs: book.object.risk_legs ?? [],
    riskSourceLabel: book.sourceLabel,
    riskSourceObjectId: book.object.object_id,
    riskSourceOrigin: String(book.object.provenance.origin ?? "strategy_lab"),
    alpha: 0.95,
    lookbackDays: book.composition?.portfolio_inputs?.lookback_days ?? 252,
    horizonDays: 1,
    mcHorizonDays: 10,
    mcSimulationModel: "Gaussian",
    mcNumSimulations: 2000,
    betaWindow: 126,
    benchmarkSymbol
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
            throw new Error("Compose or reopen a Strategy Lab experiment before opening it in Risk.");
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
