// Ideas store (Workstream 12, checkpoints I1, I2 and I3a).
//
// One place that talks to /ideas, so the Ideas tab, the shared Pin to idea
// action, Sitrep ("Promote to idea", "Your ideas") and the notification center
// all see the same board. Records are local; criterion evaluation and the
// observable preview read through the backend's read-only observable registry.

import { derived, get, writable } from "svelte/store";
import { deleteJson, getJson, getText, patchJson, postJson } from "../api/client";
import type {
  Idea,
  IdeaCreatePayload,
  IdeaCriterionPayload,
  IdeaCriterionResponse,
  IdeaEvidenceCreatePayload,
  IdeaExplanation,
  IdeaExplanationsResponse,
  IdeaListResponse,
  IdeaNotificationsResponse,
  IdeaObservablePreview,
  IdeaObservableRef,
  IdeaObservableRegistryResponse,
  IdeaPatchPayload,
  IdeaPinResponse,
  IdeaSummary,
  IdeaTrackingResponse,
  IdeaTrackingSettingsPayload,
} from "../api/types";

export const ideaList = writable<IdeaListResponse | null>(null);
export const activeIdea = writable<Idea | null>(null);
export const selectedIdeaId = writable<string | null>(null);
export const ideasLoading = writable(false);
export const ideasError = writable("");
/** The idea the last pin went to, so a run of pins from several panels lands in one place. */
export const lastPinnedIdeaId = writable<string | null>(null);
/** Triggered criteria and reviews due: the notification center and Sitrep "Your ideas". */
export const ideaNotifications = writable<IdeaNotificationsResponse | null>(null);
export const ideaObservables = writable<IdeaObservableRegistryResponse | null>(null);
/** "What is this?" texts by key, loaded once. */
export const ideaExplanations = writable<Record<string, IdeaExplanation>>({});
export const criteriaBusy = writable(false);
/** I3a: the selected idea's hypothetical forward record, rebuilt by the backend on each read. */
export const ideaTracking = writable<IdeaTrackingResponse | null>(null);
export const ideaTrackingLoading = writable(false);
export const ideaTrackingError = writable("");

/** Every idea the board knows about, newest change first. */
export const ideaSummaries = derived(ideaList, ($list): IdeaSummary[] => $list?.items ?? []);

/** Ideas a pin can go to: drafts and active ideas. */
export const pinnableIdeas = derived(ideaSummaries, ($items) =>
  $items.filter((item) => item.status === "draft" || item.status === "active")
);

/**
 * A request from anywhere in the app to open one idea in the Ideas tab.
 * App.svelte watches it and navigates; the counter makes a repeat request
 * for the same idea fire again.
 */
export const ideaOpenRequest = writable<{ ideaId: string; nonce: number } | null>(null);
let openNonce = 0;

export function requestOpenIdea(ideaId: string) {
  openNonce += 1;
  ideaOpenRequest.set({ ideaId, nonce: openNonce });
}

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

async function guarded<T>(action: () => Promise<T>): Promise<T | null> {
  try {
    const result = await action();
    ideasError.set("");
    return result;
  } catch (error) {
    ideasError.set(messageOf(error));
    return null;
  }
}

/** Load the whole board; filtering happens in the view so counts stay complete. */
export async function loadIdeas(): Promise<IdeaListResponse | null> {
  ideasLoading.set(true);
  try {
    const response = await guarded(() => getJson<IdeaListResponse>("/ideas"));
    if (response) ideaList.set(response);
    return response;
  } finally {
    ideasLoading.set(false);
  }
}

export async function ensureIdeasLoaded() {
  if (!get(ideaList)) await loadIdeas();
}

function applyIdea(idea: Idea) {
  if (get(selectedIdeaId) === idea.idea_id || get(activeIdea)?.idea_id === idea.idea_id) {
    activeIdea.set(idea);
  }
}

export async function loadIdea(ideaId: string): Promise<Idea | null> {
  selectedIdeaId.set(ideaId);
  const idea = await guarded(() => getJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}`));
  if (idea && get(selectedIdeaId) === ideaId) activeIdea.set(idea);
  if (!idea && get(selectedIdeaId) === ideaId) activeIdea.set(null);
  return idea;
}

export async function createIdea(payload: IdeaCreatePayload): Promise<Idea | null> {
  const idea = await guarded(() => postJson<Idea>("/ideas", payload));
  if (idea) await loadIdeas();
  return idea;
}

export async function patchIdea(ideaId: string, patch: IdeaPatchPayload): Promise<Idea | null> {
  const idea = await guarded(() => patchJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}`, patch));
  if (idea) {
    applyIdea(idea);
    // La fecha de revisión puede cambiar: el centro de notificaciones y Sitrep se refrescan ya.
    await Promise.all([loadIdeas(), loadIdeaNotifications()]);
  }
  return idea;
}

export async function pinEvidence(ideaId: string, payload: IdeaEvidenceCreatePayload): Promise<IdeaPinResponse | null> {
  const response = await guarded(() =>
    postJson<IdeaPinResponse>(`/ideas/${encodeURIComponent(ideaId)}/evidence`, payload)
  );
  if (response) {
    applyIdea(response.idea);
    await loadIdeas();
  }
  return response;
}

export async function unpinEvidence(ideaId: string, evidenceId: string): Promise<Idea | null> {
  const idea = await guarded(() =>
    deleteJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}/evidence/${encodeURIComponent(evidenceId)}`)
  );
  if (idea) {
    applyIdea(idea);
    await loadIdeas();
  }
  return idea;
}

export async function addIdeaJournalEntry(ideaId: string, kind: "note" | "decision", body: string) {
  const idea = await guarded(() => postJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}/journal`, { kind, body }));
  if (idea) {
    applyIdea(idea);
    await loadIdeas();
  }
  return idea;
}

export async function transitionIdea(ideaId: string, action: "activate" | "archive" | "restore") {
  const idea = await guarded(() => postJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}/${action}`, {}));
  if (idea) {
    applyIdea(idea);
    await Promise.all([loadIdeas(), loadIdeaNotifications()]);
  }
  return idea;
}

// ── Criteria, evaluation and notifications (I2) ─────────────────────────────

/** Quiet loader: the notification center must never replace the Ideas error line. */
export async function loadIdeaNotifications(): Promise<IdeaNotificationsResponse | null> {
  try {
    const response = await getJson<IdeaNotificationsResponse>("/ideas/notifications");
    ideaNotifications.set(response);
    return response;
  } catch {
    return null;
  }
}

export async function loadIdeaObservables(): Promise<IdeaObservableRegistryResponse | null> {
  const response = await guarded(() => getJson<IdeaObservableRegistryResponse>("/ideas/observables"));
  if (response) ideaObservables.set(response);
  return response;
}

/** The criteria table names each observable's source, so the registry loads with the Ideas tab. */
export async function ensureIdeaObservables() {
  if (!get(ideaObservables)) await loadIdeaObservables();
}

export async function ensureIdeaExplanations() {
  if (Object.keys(get(ideaExplanations)).length) return;
  try {
    const response = await getJson<IdeaExplanationsResponse>("/ideas/explanations");
    ideaExplanations.set(Object.fromEntries(response.items.map((item) => [item.key, item])));
  } catch {
    // The popovers fall back to "No explanation yet"; nothing else depends on them.
  }
}

async function afterCriteriaChange(idea: Idea | null) {
  if (!idea) return;
  applyIdea(idea);
  await Promise.all([loadIdeas(), loadIdeaNotifications()]);
}

async function busy<T>(action: () => Promise<T>): Promise<T> {
  criteriaBusy.set(true);
  try {
    return await action();
  } finally {
    criteriaBusy.set(false);
  }
}

export async function addCriterion(ideaId: string, payload: IdeaCriterionPayload): Promise<IdeaCriterionResponse | null> {
  return busy(async () => {
    const response = await guarded(() =>
      postJson<IdeaCriterionResponse>(`/ideas/${encodeURIComponent(ideaId)}/criteria`, payload)
    );
    await afterCriteriaChange(response?.idea ?? null);
    return response;
  });
}

export async function updateCriterion(ideaId: string, criterionId: string, payload: IdeaCriterionPayload): Promise<Idea | null> {
  return busy(async () => {
    const idea = await guarded(() =>
      patchJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}/criteria/${encodeURIComponent(criterionId)}`, payload)
    );
    await afterCriteriaChange(idea);
    return idea;
  });
}

export async function removeCriterion(ideaId: string, criterionId: string): Promise<Idea | null> {
  const idea = await guarded(() =>
    deleteJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}/criteria/${encodeURIComponent(criterionId)}`)
  );
  await afterCriteriaChange(idea);
  return idea;
}

export async function acknowledgeCriterion(ideaId: string, criterionId: string): Promise<Idea | null> {
  const idea = await guarded(() =>
    postJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}/criteria/${encodeURIComponent(criterionId)}/acknowledge`, {})
  );
  await afterCriteriaChange(idea);
  return idea;
}

/** ``open`` evaluates on-open (and never-evaluated) criteria; ``manual`` evaluates every criterion. */
export async function evaluateIdea(ideaId: string, trigger: "manual" | "open" = "manual"): Promise<Idea | null> {
  return busy(async () => {
    const idea = await guarded(() =>
      postJson<Idea>(`/ideas/${encodeURIComponent(ideaId)}/evaluate?trigger=${trigger}`, {})
    );
    await afterCriteriaChange(idea);
    return idea;
  });
}

/** Read an observable once so the criterion form can show where it stands now. */
export async function previewObservable(observable: IdeaObservableRef): Promise<IdeaObservablePreview | null> {
  try {
    return await postJson<IdeaObservablePreview>("/ideas/observables/preview", { observable });
  } catch (error) {
    ideasError.set(messageOf(error));
    return null;
  }
}

// ── Hypothetical forward tracking (I3a) ─────────────────────────────────────

let trackingRequest = 0;

/** Rebuild the selected idea's series. Errors stay in the tracking panel, not the Ideas error line. */
export async function loadIdeaTracking(ideaId: string): Promise<IdeaTrackingResponse | null> {
  const request = ++trackingRequest;
  ideaTrackingLoading.set(true);
  if (get(ideaTracking)?.idea_id !== ideaId) ideaTracking.set(null);
  try {
    const response = await getJson<IdeaTrackingResponse>(`/ideas/${encodeURIComponent(ideaId)}/tracking`);
    if (request !== trackingRequest) return response;
    ideaTracking.set(response);
    ideaTrackingError.set("");
    // El servidor guarda el titular del tablero al reconstruir la serie; el tablero lo recoge ya.
    void loadIdeas();
    return response;
  } catch (error) {
    if (request === trackingRequest) ideaTrackingError.set(messageOf(error));
    return null;
  } finally {
    if (request === trackingRequest) ideaTrackingLoading.set(false);
  }
}

/** Change the cost assumptions or the benchmark (journaled); returns the recomputed record. */
export async function updateIdeaTracking(
  ideaId: string,
  payload: IdeaTrackingSettingsPayload
): Promise<IdeaTrackingResponse | null> {
  try {
    const response = await patchJson<IdeaTrackingResponse>(`/ideas/${encodeURIComponent(ideaId)}/tracking`, payload);
    ideaTracking.set(response);
    ideaTrackingError.set("");
    // El cambio queda en el diario de la idea.
    await Promise.all([loadIdea(ideaId), loadIdeas()]);
    return response;
  } catch (error) {
    ideaTrackingError.set(messageOf(error));
    return null;
  }
}

export async function deleteIdea(ideaId: string): Promise<boolean> {
  const result = await guarded(() => deleteJson<{ success: boolean }>(`/ideas/${encodeURIComponent(ideaId)}`));
  if (!result?.success) return false;
  if (get(selectedIdeaId) === ideaId) {
    selectedIdeaId.set(null);
    activeIdea.set(null);
  }
  // Sin esto, los avisos de la idea borrada siguen visibles hasta el siguiente sondeo y abren un 404.
  await Promise.all([loadIdeas(), loadIdeaNotifications()]);
  return true;
}

/** The export text exactly as the backend renders it (Markdown with provenance, or JSON). */
export async function exportIdea(ideaId: string, format: "md" | "json"): Promise<string | null> {
  return guarded(() => getText(`/ideas/${encodeURIComponent(ideaId)}/export?format=${format}`));
}

export interface MacroEventOption {
  event_id: string;
  title: string;
  scheduled_at: string;
  region: string;
}

/** Upcoming calendar events for a "Scheduled economic event" criterion (Macro's own read path). */
export async function loadMacroEventOptions(region = "US"): Promise<MacroEventOption[]> {
  try {
    const response = await getJson<{ events: MacroEventOption[] }>(`/macro/events?region=${encodeURIComponent(region)}`);
    return (response.events ?? []).map((item) => ({
      event_id: item.event_id,
      title: item.title,
      scheduled_at: item.scheduled_at,
      region: item.region || region,
    }));
  } catch {
    return [];
  }
}
