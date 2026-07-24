import { recordRequestMetric } from "./request-metrics";

export function isAbortError(error: unknown): boolean {
  return typeof DOMException !== "undefined" && error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

type ActiveRequest<T> = {
  key: string;
  controller: AbortController;
  promise: Promise<T>;
};

/**
 * Coalesces identical work and gives each scope latest-request-wins semantics.
 * A changed key aborts the previous fetch; tasks must also check the signal
 * before committing state because some test doubles/providers ignore aborts.
 */
export class RequestCoordinator {
  private active = new Map<string, ActiveRequest<unknown>>();

  run<T>(scope: string, key: string, task: (signal: AbortSignal) => Promise<T>): Promise<T> {
    const current = this.active.get(scope) as ActiveRequest<T> | undefined;
    if (current?.key === key) {
      recordRequestMetric(key, "coalesced");
      return current.promise;
    }
    if (current) {
      recordRequestMetric(current.key, "cancelled");
      current.controller.abort();
    }

    const controller = new AbortController();
    const request: ActiveRequest<T> = {
      key,
      controller,
      promise: Promise.resolve(undefined as T)
    };
    request.promise = (async () => task(controller.signal))().finally(() => {
      if (this.active.get(scope) === request) {
        this.active.delete(scope);
      }
    });
    this.active.set(scope, request as ActiveRequest<unknown>);
    return request.promise;
  }

  cancel(scope: string): void {
    const current = this.active.get(scope);
    if (current) recordRequestMetric(current.key, "cancelled");
    current?.controller.abort();
    if (current && this.active.get(scope) === current) {
      this.active.delete(scope);
    }
  }

  isActive(scope: string): boolean {
    return this.active.has(scope);
  }

  isCurrent(scope: string, signal: AbortSignal): boolean {
    return this.active.get(scope)?.controller.signal === signal;
  }
}
