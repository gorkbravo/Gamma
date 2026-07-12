import { describe, expect, it } from "vitest";
import { RequestCoordinator } from "./request-coordinator";

describe("RequestCoordinator", () => {
  it("coalesces identical work and aborts superseded work", async () => {
    const coordinator = new RequestCoordinator();
    let resolveFirst!: (value: string) => void;
    let firstSignal: AbortSignal | null = null;
    const first = coordinator.run("overview", "A", (signal) => {
      firstSignal = signal;
      return new Promise<string>((resolve) => { resolveFirst = resolve; });
    });
    const duplicate = coordinator.run("overview", "A", async () => "duplicate");
    expect(duplicate).toBe(first);

    const second = coordinator.run("overview", "B", async (signal) => {
      expect(signal.aborted).toBe(false);
      return "new";
    });
    expect((firstSignal as AbortSignal | null)?.aborted).toBe(true);
    resolveFirst("old");
    await expect(first).resolves.toBe("old");
    await expect(second).resolves.toBe("new");
  });
});
