import { describe, expect, it, vi } from "vitest";
import { hydrateActiveWorkspace, type ActiveWorkspaceHydration } from "./bootstrap";

function loaders(): ActiveWorkspaceHydration {
  return Object.fromEntries([
    "portfolio", "sitrep", "equityResearch", "strategyLab", "macro", "commodities",
    "predictionMarkets", "crypto", "fundamentals", "maritime", "copilot", "risk", "iv"
  ].map((key) => [key, vi.fn().mockResolvedValue(undefined)])) as unknown as ActiveWorkspaceHydration;
}

describe("active workspace hydration", () => {
  it("does not hydrate Portfolio while restoring Research", async () => {
    const calls = loaders();
    await hydrateActiveWorkspace("macro", null, calls);
    expect(calls.macro).toHaveBeenCalledTimes(1);
    expect(calls.portfolio).not.toHaveBeenCalled();
    expect(calls.sitrep).not.toHaveBeenCalled();
  });

  it("hydrates Portfolio while disconnected so local history remains available", async () => {
    const calls = loaders();
    await hydrateActiveWorkspace("portfolio", null, calls);
    expect(calls.portfolio).toHaveBeenCalledTimes(1);
    await hydrateActiveWorkspace("portfolio", {
      mock_mode: true,
      connection: { connected: false }
    } as never, calls);
    expect(calls.portfolio).toHaveBeenCalledTimes(2);
  });
});
