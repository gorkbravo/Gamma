<script lang="ts">
  // Idea drafts proposed by Copilot (Workstream 12, I5). A proposal is a
  // pending draft change: nothing exists until the user accepts it here, and
  // accepting creates a draft idea, never an active one. Accept and reject go
  // through the existing confirmation flow (token, session and proposal hash).
  import { onMount } from "svelte";
  import { getJson, postJson } from "../lib/api/client";
  import type { CopilotDraftMutation, CopilotMutationApplyResult, CopilotResearchCardResult } from "../lib/api/types";
  import { proposalCriteria, proposalLegs, proposalStatusLabel, proposalsForResult } from "../lib/copilot-idea-proposals";
  import { loadIdeas, requestOpenIdea } from "../lib/stores/ideas";

  export let result: CopilotResearchCardResult;
  export let fetchMutation: (mutationId: string) => Promise<CopilotDraftMutation> = (mutationId) =>
    getJson<CopilotDraftMutation>(`/copilot/mutations/${encodeURIComponent(mutationId)}`);

  let proposals: CopilotDraftMutation[] = proposalsForResult(result, []);
  let busyId: string | null = null;
  let errors: Record<string, string> = {};
  let created: Record<string, string> = {};

  // Tras recargar la sesión solo quedan los ids: se lee el estado actual de cada propuesta.
  onMount(async () => {
    const missing = (result.proposal_ids ?? []).filter((id) => !proposals.some((item) => item.mutation_id === id));
    if (!missing.length) return;
    const fetched: CopilotDraftMutation[] = [];
    for (const id of missing) {
      try {
        fetched.push(await fetchMutation(id));
      } catch {
        // Una propuesta borrada o caducada simplemente no se muestra.
      }
    }
    proposals = proposalsForResult(result, fetched);
  });

  function replaceProposal(next: CopilotDraftMutation) {
    proposals = proposals.map((item) => (item.mutation_id === next.mutation_id ? next : item));
  }

  async function accept(proposal: CopilotDraftMutation) {
    busyId = proposal.mutation_id;
    errors = { ...errors, [proposal.mutation_id]: "" };
    try {
      const applied = await postJson<CopilotMutationApplyResult>(`/copilot/mutations/${encodeURIComponent(proposal.mutation_id)}/apply`, {
        confirmation_token: proposal.confirmation_token,
        user_session_id: proposal.session_id ?? null,
        context_fingerprint: proposal.context_fingerprint ?? null,
        proposal_hash: proposal.proposal_hash ?? null,
      });
      replaceProposal(applied.mutation);
      const ideaId = String(applied.artifact?.idea_id ?? "");
      if (ideaId) created = { ...created, [proposal.mutation_id]: ideaId };
      await loadIdeas();
    } catch (error) {
      errors = { ...errors, [proposal.mutation_id]: error instanceof Error ? error.message : String(error) };
    } finally {
      busyId = null;
    }
  }

  async function reject(proposal: CopilotDraftMutation) {
    busyId = proposal.mutation_id;
    errors = { ...errors, [proposal.mutation_id]: "" };
    try {
      replaceProposal(
        await postJson<CopilotDraftMutation>(`/copilot/mutations/${encodeURIComponent(proposal.mutation_id)}/reject`, {
          user_session_id: proposal.session_id ?? null,
        })
      );
    } catch (error) {
      errors = { ...errors, [proposal.mutation_id]: error instanceof Error ? error.message : String(error) };
    } finally {
      busyId = null;
    }
  }
</script>

{#each proposals as proposal (proposal.mutation_id)}
  {@const payload = proposal.proposed_payload}
  <section class="idea-proposal" aria-label="Drafted idea">
    <header class="proposal-head">
      <strong>Drafted idea</strong>
      <span class="tag" class:accent={proposal.status === "pending"} class:positive={proposal.status === "applied"} class:warning={proposal.status === "failed" || proposal.status === "expired"}>
        {proposalStatusLabel(proposal.status)}
      </span>
      <span class="head-meta">Nothing is created until you accept it; an accepted draft is not activated.</span>
    </header>
    <div class="proposal-body">
      <p class="proposal-title">{String(payload.title ?? proposal.target_label)}</p>
      <p class="proposal-thesis">{String(payload.thesis ?? "")}</p>
      <dl class="proposal-facts">
        <div><dt>Stance</dt><dd>{String(payload.stance ?? "N/A")}</dd></div>
        <div><dt>Legs</dt><dd>{proposalLegs(payload) || "None"}</dd></div>
      </dl>
      <table class="data-table is-compact is-top proposal-criteria">
        <thead><tr><th>Kind</th><th>Criterion</th><th>Why</th></tr></thead>
        <tbody>
          {#each proposalCriteria(payload) as row, index (index)}
            <tr><td>{row.kind}</td><td>{row.label}</td><td class="why-cell">{row.rationale || "N/A"}</td></tr>
          {/each}
        </tbody>
      </table>
      {#if proposal.rationale}<p class="proposal-note">Grounded in: {proposal.rationale}</p>{/if}
      {#if proposal.warnings.length}
        <ul class="proposal-warnings">{#each proposal.warnings as warning (warning)}<li>{warning}</li>{/each}</ul>
      {/if}
    </div>
    <div class="proposal-actions">
      {#if proposal.status === "pending"}
        <button type="button" class="btn is-small is-ghost" disabled={busyId != null} on:click={() => reject(proposal)}>Reject</button>
        <button type="button" class="btn is-small is-primary" disabled={busyId != null} on:click={() => accept(proposal)}>
          {busyId === proposal.mutation_id ? "Creating…" : "Create draft idea"}
        </button>
      {:else if created[proposal.mutation_id] || (proposal.status === "applied" && proposal.target_id !== "new_idea")}
        <button type="button" class="btn is-small" on:click={() => requestOpenIdea(created[proposal.mutation_id] ?? proposal.target_id)}>Open idea</button>
      {/if}
    </div>
    {#if errors[proposal.mutation_id]}<p class="proposal-error" role="alert">{errors[proposal.mutation_id]}</p>{/if}
  </section>
{/each}

<style>
  .idea-proposal {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-4) 0;
    border-top: 1px solid var(--divider);
  }

  .proposal-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
    font-size: var(--text-sm);
  }

  .proposal-head strong {
    font-weight: 600;
  }

  .head-meta {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .proposal-body {
    display: grid;
    gap: var(--space-2);
    min-width: 0;
  }

  .proposal-title {
    margin: 0;
    font-weight: 600;
  }

  .proposal-thesis,
  .proposal-note {
    margin: 0;
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .proposal-facts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-6);
    margin: 0;
  }

  .proposal-facts dt {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
  }

  .proposal-facts dd {
    margin: 0;
    font-size: var(--text-sm);
  }

  .proposal-criteria {
    width: 100%;
  }

  .why-cell {
    color: var(--text-2);
  }

  .proposal-warnings {
    margin: 0;
    padding-left: var(--space-5);
    color: var(--warning);
    font-size: var(--text-xs);
  }

  .proposal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .proposal-error {
    margin: 0;
    color: var(--negative);
    font-size: var(--text-xs);
  }
</style>
