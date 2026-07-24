import type { SystemStatus, TabId } from "../api/types";

export type ActiveWorkspaceHydration = {
  portfolio: () => Promise<unknown>;
  sitrep: () => Promise<unknown>;
  equityResearch: () => Promise<unknown>;
  strategyLab: () => Promise<unknown>;
  macro: () => Promise<unknown>;
  commodities: () => Promise<unknown>;
  predictionMarkets: () => Promise<unknown>;
  crypto: () => Promise<unknown>;
  fundamentals: () => Promise<unknown>;
  maritime: () => Promise<unknown>;
  copilot: () => Promise<unknown>;
  risk: () => Promise<unknown>;
  iv: () => Promise<unknown>;
};

/** Hydrates only the restored visible domain. Shell diagnostics/settings remain user-activated. */
export async function hydrateActiveWorkspace(
  tab: TabId,
  status: SystemStatus | null,
  loaders: ActiveWorkspaceHydration
): Promise<void> {
  if (tab === "portfolio") {
    if (status?.mock_mode || status?.connection.connected) await loaders.portfolio();
    return;
  }
  const loader: Record<Exclude<TabId, "portfolio">, () => Promise<unknown>> = {
    sitrep: loaders.sitrep,
    equity_research: loaders.equityResearch,
    strategy_lab: loaders.strategyLab,
    macro: loaders.macro,
    commodities: loaders.commodities,
    prediction_markets: loaders.predictionMarkets,
    crypto: loaders.crypto,
    fundamentals: loaders.fundamentals,
    maritime: loaders.maritime,
    copilot: loaders.copilot,
    risk: loaders.risk,
    iv: loaders.iv
  };
  await loader[tab]();
}
