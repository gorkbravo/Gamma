import { RequestCoordinator, isAbortError } from "./request-coordinator";
import { recordRequestMetric } from "./request-metrics";
import { writable } from "svelte/store";

export type QueryCacheState = "cached" | "stale" | "refreshed" | "network";

export type QueryCacheMetadata = {
  state: QueryCacheState;
  key: string;
  cachedAt: string;
  refreshedAt: string | null;
};

type CacheEntry<T> = {
  data: T;
  storedAt: number;
  generation: number;
};

export type QueryOptions<T> = {
  scope: string;
  key: string;
  staleTimeMs: number;
  fetcher: (signal: AbortSignal) => Promise<T>;
  onData?: (data: T, metadata: QueryCacheMetadata) => void;
  forceRefresh?: boolean;
  staleWhileRevalidate?: boolean;
};

const MAX_ENTRIES = 150;
export const queryStates = writable<Record<string, QueryCacheMetadata>>({});

export class FrontendQueryCache {
  private entries = new Map<string, CacheEntry<unknown>>();
  private generations = new Map<string, number>();
  private coordinator = new RequestCoordinator();

  query<T>(options: QueryOptions<T>): Promise<T> {
    const cached = this.entries.get(options.key) as CacheEntry<T> | undefined;
    const ageMs = cached ? Date.now() - cached.storedAt : Number.POSITIVE_INFINITY;
    if (cached && !options.forceRefresh && ageMs <= options.staleTimeMs) {
      recordRequestMetric(options.key, "cache_hit");
      const data = annotate(cached.data, options.key, cached.storedAt, "cached");
      const state = metadata(options.key, cached.storedAt, "cached");
      queryStates.update((current) => ({ ...current, [options.key]: state }));
      options.onData?.(data, state);
      return Promise.resolve(data);
    }
    if (cached && !options.forceRefresh && options.staleWhileRevalidate !== false) {
      recordRequestMetric(options.key, "stale_hit");
      const stale = annotate(cached.data, options.key, cached.storedAt, "stale");
      const state = metadata(options.key, cached.storedAt, "stale");
      queryStates.update((current) => ({ ...current, [options.key]: state }));
      options.onData?.(stale, state);
      void this.refresh(options, cached).catch(() => undefined);
      return Promise.resolve(stale);
    }
    return this.refresh(options, cached);
  }

  invalidate(prefix: string): void {
    for (const key of this.entries.keys()) {
      if (key.startsWith(prefix)) this.entries.delete(key);
    }
  }

  clear(): void {
    this.entries.clear();
    queryStates.set({});
  }

  private refresh<T>(options: QueryOptions<T>, stale: CacheEntry<T> | undefined): Promise<T> {
    return this.coordinator.run(options.scope, options.key, async (signal) => {
      const generation = (this.generations.get(options.key) ?? 0) + 1;
      this.generations.set(options.key, generation);
      try {
        const data = await options.fetcher(signal);
        if (signal.aborted) throw abortError();
        if (this.generations.get(options.key) !== generation) return data;
        const storedAt = Date.now();
        this.setEntry(options.key, { data, storedAt, generation });
        const state: QueryCacheState = stale ? "refreshed" : "network";
        const annotated = annotate(data, options.key, storedAt, state);
        const cacheMetadata = metadata(options.key, storedAt, state);
        queryStates.update((current) => ({ ...current, [options.key]: cacheMetadata }));
        options.onData?.(annotated, cacheMetadata);
        return annotated;
      } catch (error) {
        if (isAbortError(error)) throw error;
        if (stale) {
          recordRequestMetric(options.key, "stale_hit");
          const fallback = annotate(stale.data, options.key, stale.storedAt, "stale", error);
          const state = metadata(options.key, stale.storedAt, "stale");
          queryStates.update((current) => ({ ...current, [options.key]: state }));
          options.onData?.(fallback, state);
          return fallback;
        }
        throw error;
      }
    });
  }

  private setEntry<T>(key: string, entry: CacheEntry<T>): void {
    if (!this.entries.has(key) && this.entries.size >= MAX_ENTRIES) {
      this.entries.delete(this.entries.keys().next().value as string);
    }
    this.entries.set(key, entry);
  }
}

export function stableQueryKey(endpoint: string, params: Record<string, unknown> = {}): string {
  const normalized = Object.entries(params)
    .filter(([, value]) => value !== undefined)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(normalizeValue(value))}`)
    .join("&");
  return normalized ? `${endpoint}?${normalized}` : endpoint;
}

function normalizeValue(value: unknown): string {
  if (Array.isArray(value)) return [...value].map(normalizeValue).sort().join(",");
  if (value && typeof value === "object") {
    return JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))));
  }
  return String(value ?? "");
}

function annotate<T>(data: T, key: string, storedAt: number, state: QueryCacheState, error?: unknown): T {
  void key;
  void storedAt;
  if (state !== "stale") return data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return data;
  const source = data as Record<string, unknown>;
  const warning = error
    ? `Refresh failed; showing the most recent usable cached payload. ${error instanceof Error ? error.message : String(error)}`
    : state === "stale"
      ? "Showing stale cached data while Gamma refreshes it in the background."
      : null;
  const warnings = Array.isArray(source.warnings) ? [...source.warnings] : [];
  if (warning && !warnings.includes(warning)) warnings.push(warning);
  return {
    ...source,
    ...(warning ? { warnings } : {}),
    ...(state === "stale" && "freshness_label" in source ? { freshness_label: "stale" } : {})
  } as T;
}

function metadata(key: string, storedAt: number, state: QueryCacheState): QueryCacheMetadata {
  return {
    state,
    key,
    cachedAt: new Date(storedAt).toISOString(),
    refreshedAt: state === "network" || state === "refreshed" ? new Date().toISOString() : null
  };
}

function abortError(): Error {
  const error = new Error("Request aborted");
  error.name = "AbortError";
  return error;
}

export const queryCache = new FrontendQueryCache();
