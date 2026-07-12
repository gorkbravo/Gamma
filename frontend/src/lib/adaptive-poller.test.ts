import { afterEach, describe, expect, it, vi } from "vitest";
import { createAdaptivePoller } from "./adaptive-poller";

afterEach(() => {
  vi.useRealTimers();
});

describe("createAdaptivePoller", () => {
  it("backs off after failures and never overlaps work", async () => {
    vi.useFakeTimers();
    let release!: () => void;
    const task = vi.fn()
      .mockImplementationOnce(() => new Promise<boolean>((resolve) => { release = () => resolve(false); }))
      .mockResolvedValue(true);
    const poller = createAdaptivePoller({ task, baseDelayMs: 100, maxDelayMs: 800 });

    poller.start();
    await vi.advanceTimersByTimeAsync(0);
    poller.trigger();
    await vi.advanceTimersByTimeAsync(0);
    expect(task).toHaveBeenCalledTimes(1);
    release();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(199);
    expect(task).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(task).toHaveBeenCalledTimes(2);
    poller.stop();
  });

  it("pauses while hidden and resumes on trigger", async () => {
    vi.useFakeTimers();
    let visible = false;
    const task = vi.fn().mockResolvedValue(true);
    const poller = createAdaptivePoller({ task, baseDelayMs: 100, maxDelayMs: 800, isVisible: () => visible });
    poller.start();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(task).not.toHaveBeenCalled();
    visible = true;
    poller.trigger();
    await vi.advanceTimersByTimeAsync(0);
    expect(task).toHaveBeenCalledTimes(1);
    poller.stop();
  });
});
