// Ideas store (Workstream 12, checkpoint I1).
//
// One place that talks to /ideas, so the Ideas tab, the shared Pin to idea
// action and Sitrep's "Promote to idea" all see the same board. Every call is
// a local read or write of research records; none touches a provider.

import { derived, get, writable } from "svelte/store";
import { deleteJson, getJson, getText, patchJson, postJson } from "../api/client";
import type {
  Idea,
  IdeaCreatePayload,
  IdeaEvidenceCreatePayload,
  IdeaListResponse,
  IdeaPatchPayload,
  IdeaPinResponse,
  IdeaSummary,
} from "../api/types";

export const ideaList = writable<IdeaListResponse | null>(null);
export const activeIdea = writable<Idea | null>(null);
export const selectedIdeaId = writable<string | null>(null);
export const ideasLoading = writable(false);
export const ideasError = writable("");
/** The idea the last pin went to, so a run of pins from several panels lands in one place. */
export const lastPinnedIdeaId = writable<string | null>(null);

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
    await loadIdeas();
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
    await loadIdeas();
  }
  return idea;
}

export async function deleteIdea(ideaId: string): Promise<boolean> {
  const result = await guarded(() => deleteJson<{ success: boolean }>(`/ideas/${encodeURIComponent(ideaId)}`));
  if (!result?.success) return false;
  if (get(selectedIdeaId) === ideaId) {
    selectedIdeaId.set(null);
    activeIdea.set(null);
  }
  await loadIdeas();
  return true;
}

/** The export text exactly as the backend renders it (Markdown with provenance, or JSON). */
export async function exportIdea(ideaId: string, format: "md" | "json"): Promise<string | null> {
  return guarded(() => getText(`/ideas/${encodeURIComponent(ideaId)}/export?format=${format}`));
}
