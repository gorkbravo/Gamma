export type PollResult = boolean | { ok: boolean; nextDelayMs?: number };

export interface AdaptivePoller {
  start(): void;
  stop(): void;
  trigger(): void;
  readonly running: boolean;
}

export function createAdaptivePoller(options: {
  task: () => Promise<PollResult>;
  baseDelayMs: number;
  maxDelayMs: number;
  runImmediately?: boolean;
  isVisible?: () => boolean;
}): AdaptivePoller {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let started = false;
  let inFlight = false;
  let failureCount = 0;
  const isVisible = options.isVisible ?? (() => typeof document === "undefined" || !document.hidden);

  function clearTimer() {
    if (timer != null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function schedule(delayMs: number) {
    clearTimer();
    if (!started || !isVisible()) return;
    timer = setTimeout(run, Math.max(0, delayMs));
  }

  async function run() {
    timer = null;
    if (!started || inFlight || !isVisible()) return;
    inFlight = true;
    let result: PollResult = false;
    try {
      result = await options.task();
    } catch {
      result = false;
    } finally {
      inFlight = false;
    }
    if (!started || !isVisible()) return;
    const normalized = typeof result === "boolean" ? { ok: result } : result;
    failureCount = normalized.ok ? 0 : failureCount + 1;
    const backoff = Math.min(options.maxDelayMs, options.baseDelayMs * 2 ** failureCount);
    schedule(normalized.nextDelayMs ?? (normalized.ok ? options.baseDelayMs : backoff));
  }

  function handleVisibilityChange() {
    if (!started) return;
    if (isVisible()) {
      schedule(0);
    } else {
      clearTimer();
    }
  }

  return {
    get running() {
      return started;
    },
    start() {
      if (started) return;
      started = true;
      if (typeof document !== "undefined") {
        document.addEventListener("visibilitychange", handleVisibilityChange);
      }
      schedule(options.runImmediately === false ? options.baseDelayMs : 0);
    },
    stop() {
      if (!started) return;
      started = false;
      clearTimer();
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", handleVisibilityChange);
      }
    },
    trigger() {
      if (started && !inFlight) schedule(0);
    }
  };
}
