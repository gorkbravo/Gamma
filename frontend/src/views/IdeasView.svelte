<script lang="ts">
  // Ideas tab (Workstream 12, checkpoints I1, I2, I3a and I3b): Board lists
  // every idea in one dense table with its criterion states and its
  // hypothetical forward return; Idea shows one thesis with its frozen
  // evidence grouped by stance, its criteria and their live state, its review
  // when closed, its hypothetical tracking and its append-only journal; Review
  // describes the closed record. The backend evaluates criteria and rebuilds
  // the tracked series read-only; this view never calls a provider itself.
  import IdeaAnalysisPanel from "../components/IdeaAnalysisPanel.svelte";
  import IdeaCloseForm from "../components/IdeaCloseForm.svelte";
  import IdeaCriteriaPanel from "../components/IdeaCriteriaPanel.svelte";
  import IdeaReviewMode from "../components/IdeaReviewMode.svelte";
  import IdeaReviewSection from "../components/IdeaReviewSection.svelte";
  import IdeaTrackingPanel from "../components/IdeaTrackingPanel.svelte";
  import ProvenanceBadge from "../components/ProvenanceBadge.svelte";
  import WhatIsThis from "../components/WhatIsThis.svelte";
  import type {
    CrossTabHandoffEnvelope,
    Idea,
    IdeaClosePayload,
    IdeaCreatePayload,
    IdeaCriterionPayload,
    IdeaEvidence,
    IdeaEvidenceStance,
    IdeaJournalEntry,
    IdeaLeg,
    IdeaListResponse,
    IdeaObservablePreview,
    IdeaObservableRef,
    IdeaObservableRegistryResponse,
    IdeaPatchPayload,
    IdeaReviewStatsResponse,
    IdeaStance,
    IdeaSummary,
    IdeaTrackingResponse,
    IdeaTrackingSettingsPayload,
  } from "../lib/api/types";
  import {
    EVIDENCE_STANCE_LABELS,
    IDEA_BOARD_FILTERS,
    IDEA_EVIDENCE_STANCES,
    IDEA_STANCES,
    IDEA_STANCE_LABELS,
    IDEA_STATUS_LABELS,
    boardFilterStatuses,
    capturedMetricPairs,
    capturedValuesExtraCount,
    formatIdeaInstant,
    formatLegs,
    groupEvidenceByStance,
    handoffPlaceLabel,
    ideaExportFilename,
    ideaStatusTone,
    journalKindLabel,
    parseTagInput,
    pinBadgeData,
    type IdeaBoardFilter,
  } from "../lib/ideas";
  import { toProvenanceBadge } from "../lib/provenance";
  import { activateRowOnKey } from "../lib/row-activation";
  import { CRITERION_STATE_LABELS, criteriaSummary, daysToReview, daysToReviewText } from "../lib/idea-criteria";
  import { TRACKING_LABEL, boardTrackingCell } from "../lib/idea-tracking";
  import { reviewKpis } from "../lib/idea-review";

  export let mode: "board" | "idea" | "review" = "board";
  export let list: IdeaListResponse | null = null;
  export let idea: Idea | null = null;
  export let loading = false;
  export let errorMessage = "";
  export let onOpenIdea: (ideaId: string) => void | Promise<void> = () => {};
  export let onCreateIdea: (payload: IdeaCreatePayload) => Promise<Idea | null> = async () => null;
  export let onPatchIdea: (ideaId: string, patch: IdeaPatchPayload) => Promise<Idea | null> = async () => null;
  export let onUnpinEvidence: (ideaId: string, evidenceId: string) => Promise<Idea | null> = async () => null;
  export let onAddJournalEntry: (ideaId: string, kind: "note" | "decision", body: string) => Promise<Idea | null> =
    async () => null;
  export let onTransition: (ideaId: string, action: "activate" | "archive" | "restore" | "reopen") => Promise<Idea | null> =
    async () => null;
  export let onDeleteIdea: (ideaId: string) => Promise<boolean> = async () => false;
  export let onExportIdea: (ideaId: string, format: "md" | "json") => Promise<string | null> = async () => null;
  export let onReopen: (envelope: CrossTabHandoffEnvelope) => void | Promise<void> = () => {};
  // I2: criteria, evaluation and the observable registry.
  export let observables: IdeaObservableRegistryResponse | null = null;
  export let criteriaBusy = false;
  export let onLoadObservables: () => void | Promise<unknown> = () => {};
  export let onSaveCriterion: (ideaId: string, criterionId: string | null, payload: IdeaCriterionPayload) => Promise<boolean> =
    async () => false;
  export let onRemoveCriterion: (ideaId: string, criterionId: string) => Promise<unknown> = async () => null;
  export let onAcknowledgeCriterion: (ideaId: string, criterionId: string) => Promise<unknown> = async () => null;
  export let onEvaluateIdea: (ideaId: string) => Promise<unknown> = async () => null;
  export let onPreviewObservable: (observable: IdeaObservableRef) => Promise<IdeaObservablePreview | null> = async () => null;
  export let onLoadEvents: () => Promise<Array<{ event_id: string; title: string; scheduled_at: string; region: string }>> = async () => [];
  // I3a: hypothetical forward tracking of the selected idea.
  export let tracking: IdeaTrackingResponse | null = null;
  export let trackingLoading = false;
  export let trackingError = "";
  export let onLoadTracking: (ideaId: string) => Promise<unknown> | void = () => {};
  export let onUpdateTracking: (ideaId: string, payload: IdeaTrackingSettingsPayload) => Promise<IdeaTrackingResponse | null> =
    async () => null;
  // I3b: close with a review, and the Review mode.
  export let reviewStats: IdeaReviewStatsResponse | null = null;
  export let onLoadReview: () => Promise<unknown> | void = () => {};
  export let onCloseIdea: (ideaId: string, payload: IdeaClosePayload) => Promise<Idea | null> = async () => null;
  // I3c: test and risk snapshots, run only when the user asks.
  export let analysisBusy: "" | "test" | "risk" = "";
  export let analysisError = "";
  export let onRunTest: (ideaId: string) => Promise<unknown> | void = () => {};
  export let onRunRisk: (ideaId: string) => Promise<unknown> | void = () => {};

  const modes: Array<{ id: "board" | "idea" | "review"; label: string }> = [
    { id: "board", label: "Board" },
    { id: "idea", label: "Idea" },
    { id: "review", label: "Review" },
  ];

  // Review se recalcula cada vez que se entra en el modo: los cierres pueden haber cambiado.
  // Un único disparador: al montar en Review y cada vez que se entra en el modo.
  let previousMode: typeof mode | null = null;
  $: if (mode !== previousMode) {
    previousMode = mode;
    if (mode === "review") void onLoadReview();
  }

  // ── Board ──────────────────────────────────────────────────────────────
  let filter: IdeaBoardFilter = "open";
  let tagFilter = "";
  let createOpen = false;
  let createTitle = "";
  let createStance: IdeaStance = "neutral";
  let creating = false;

  $: summaries = list?.items ?? [];
  $: statusCounts = list?.status_counts ?? { draft: 0, active: 0, closed: 0, archived: 0 };
  $: filterStatuses = boardFilterStatuses(filter);
  // Ideas with an unacknowledged trigger come first; otherwise newest change first.
  $: boardRows = summaries
    .filter(
      (row) =>
        (!filterStatuses.length || filterStatuses.includes(row.status)) && (!tagFilter || row.tags.includes(tagFilter))
    )
    .map((row, index) => ({ row, index }))
    .sort((left, right) => Number((right.row.unacknowledged_triggers ?? 0) > 0) - Number((left.row.unacknowledged_triggers ?? 0) > 0) || left.index - right.index)
    .map((item) => item.row);
  $: totalPins = summaries.reduce((sum, row) => sum + row.evidence_total, 0);
  $: totalTriggered = summaries.reduce((sum, row) => sum + (row.status === "active" ? row.unacknowledged_triggers ?? 0 : 0), 0);
  // A one-time schema migration is not a problem to act on; quarantines and skipped files are.
  $: storageWarnings = (list?.storage_warnings ?? []).filter((warning) => warning.action !== "migrated");
  $: if (tagFilter && list && !list.tags.includes(tagFilter)) tagFilter = "";

  async function submitCreate() {
    const title = createTitle.trim();
    if (!title || creating) return;
    creating = true;
    try {
      const created = await onCreateIdea({ title, stance: createStance });
      if (created) {
        createTitle = "";
        createStance = "neutral";
        createOpen = false;
        await onOpenIdea(created.idea_id);
      }
    } finally {
      creating = false;
    }
  }

  // ── Idea ───────────────────────────────────────────────────────────────
  interface LegRow {
    label: string;
    normalized_id: string;
    entity_type: string;
    weight: string;
  }

  let editing = false;
  let editingId: string | null = null;
  let saving = false;
  let formTitle = "";
  let formThesis = "";
  let formStance: IdeaStance = "neutral";
  let formNotes = "";
  let formTags = "";
  let formReviewDate = "";
  let formWindow = "";
  let formLegs: LegRow[] = [];
  let confirmDelete = false;
  let confirmUnpin: string | null = null;
  let journalKind: "note" | "decision" = "note";
  let journalBody = "";
  let journalSaving = false;
  let exportError = "";
  let expandedPins: string[] = [];
  let closing = false;

  async function submitClose(payload: IdeaClosePayload): Promise<boolean> {
    if (!idea) return false;
    const closed = await onCloseIdea(idea.idea_id, payload);
    if (closed) closing = false;
    return Boolean(closed);
  }

  function toggleExpanded(evidenceId: string) {
    expandedPins = expandedPins.includes(evidenceId)
      ? expandedPins.filter((id) => id !== evidenceId)
      : [...expandedPins, evidenceId];
  }

  $: groups = groupEvidenceByStance(idea?.evidence ?? []);
  $: journalNewestFirst = [...(idea?.journal ?? [])].reverse();
  // Leaving the idea (or opening another) drops any half-finished edit.
  $: if (idea?.idea_id !== editingId) {
    editing = false;
    closing = false;
    confirmDelete = false;
    confirmUnpin = null;
    editingId = idea?.idea_id ?? null;
  }

  function startEdit() {
    if (!idea) return;
    formTitle = idea.title;
    formThesis = idea.thesis;
    formStance = idea.stance;
    formNotes = idea.notes;
    formTags = idea.tags.join(", ");
    formReviewDate = idea.horizon.review_date ?? "";
    formWindow = idea.horizon.holding_window ?? "";
    formLegs = idea.legs.map((leg) => ({
      label: leg.entity.label,
      normalized_id: leg.entity.normalized_id,
      entity_type: leg.entity.entity_type,
      weight: leg.weight == null ? "" : String(leg.weight),
    }));
    editing = true;
  }

  function addLegRow() {
    formLegs = [...formLegs, { label: "", normalized_id: "", entity_type: "equity", weight: "" }];
  }

  function removeLegRow(index: number) {
    formLegs = formLegs.filter((_, position) => position !== index);
  }

  $: legErrors = formLegs.map((row) => {
    if (!row.label.trim() && !row.normalized_id.trim()) return "";
    if (!row.normalized_id.trim()) return "Id required";
    if (row.weight.trim() && !Number.isFinite(Number(row.weight))) return "Weight must be a number";
    return "";
  });
  $: canSave = Boolean(formTitle.trim()) && legErrors.every((message) => !message) && !saving;

  function legsFromForm(): IdeaLeg[] {
    return formLegs
      .filter((row) => row.normalized_id.trim())
      .map((row) => ({
        entity: {
          entity_type: row.entity_type.trim() || "equity",
          label: row.label.trim() || row.normalized_id.trim(),
          normalized_id: row.normalized_id.trim().toUpperCase(),
          provider_id: null,
          native_id: null,
          metadata: {},
        },
        weight: row.weight.trim() ? Number(row.weight) : null,
      }));
  }

  async function saveEdit() {
    if (!idea || !canSave) return;
    saving = true;
    try {
      const updated = await onPatchIdea(idea.idea_id, {
        title: formTitle.trim(),
        thesis: formThesis.trim(),
        stance: formStance,
        notes: formNotes,
        tags: parseTagInput(formTags),
        legs: legsFromForm(),
        horizon: { review_date: formReviewDate || null, holding_window: formWindow.trim() || null },
      });
      if (updated) editing = false;
    } finally {
      saving = false;
    }
  }

  async function submitJournal() {
    if (!idea || !journalBody.trim() || journalSaving) return;
    journalSaving = true;
    try {
      const updated = await onAddJournalEntry(idea.idea_id, journalKind, journalBody.trim());
      if (updated) journalBody = "";
    } finally {
      journalSaving = false;
    }
  }

  async function unpin(evidence: IdeaEvidence) {
    if (!idea) return;
    if (confirmUnpin !== evidence.evidence_id) {
      confirmUnpin = evidence.evidence_id;
      return;
    }
    confirmUnpin = null;
    await onUnpinEvidence(idea.idea_id, evidence.evidence_id);
  }

  async function removeIdea() {
    if (!idea) return;
    if (!confirmDelete) {
      confirmDelete = true;
      return;
    }
    confirmDelete = false;
    const deleted = await onDeleteIdea(idea.idea_id);
    if (deleted) mode = "board";
  }

  async function download(format: "md" | "json") {
    if (!idea || typeof document === "undefined") return;
    exportError = "";
    const content = await onExportIdea(idea.idea_id, format);
    if (content == null) {
      exportError = "Export failed.";
      return;
    }
    const type = format === "md" ? "text/markdown;charset=utf-8" : "application/json;charset=utf-8";
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = ideaExportFilename(idea.title, idea.idea_id, format);
    link.click();
    URL.revokeObjectURL(url);
  }

  function horizonText(current: Idea): string {
    const parts = [current.horizon.review_date ? `Review ${current.horizon.review_date}` : "", current.horizon.holding_window ?? ""];
    return parts.filter(Boolean).join(" · ") || "Not set";
  }

  function entryDetail(entry: IdeaJournalEntry): string[] {
    const changes = entry.details?.changes;
    if (!Array.isArray(changes)) return [];
    return changes.map((change) => {
      const record = change as Record<string, unknown>;
      if (record.field === "notes") return `Notes ${record.before_length ?? 0} → ${record.after_length ?? 0} characters`;
      const before = String(record.before ?? "") || "empty";
      const after = String(record.after ?? "") || "empty";
      return `${String(record.field)}: ${before} → ${after}`;
    });
  }

  function reopenTitle(evidence: IdeaEvidence): string {
    if (!evidence.reopen) return "This pin has no source to reopen.";
    const entity = evidence.reopen.selected_entity?.label;
    return `Open ${handoffPlaceLabel(evidence.reopen, "target")}${entity ? ` on ${entity}` : ""}`;
  }

  function stanceEmpty(stance: IdeaEvidenceStance): string {
    if (stance === "supports") return "No supporting evidence pinned yet.";
    if (stance === "challenges") return "No challenging evidence pinned yet. Disconfirming evidence belongs here.";
    return "No context pinned yet.";
  }

  function boardSubtitle(): string {
    if (loading && !list) return "Loading…";
    const total = list?.total ?? 0;
    return `${total} ${total === 1 ? "idea" : "ideas"} · stored locally`;
  }

  $: ideaReviewDays = idea ? daysToReview(idea.horizon.review_date) : null;
  $: reviewCounts = reviewKpis(reviewStats);
  $: headerKpis =
    mode === "review"
      ? [
          { label: "Reviewed", value: String(reviewCounts.reviewed), tone: "", explain: "" },
          { label: "Confirmed", value: String(reviewCounts.confirmed), tone: "", explain: "" },
          { label: "Invalidated", value: String(reviewCounts.invalidated), tone: "", explain: "" },
          { label: "Abandoned", value: String(reviewCounts.abandoned), tone: "", explain: "" },
          { label: "Expired", value: String(reviewCounts.expired), tone: "", explain: "" },
        ]
      : mode === "idea" && idea
      ? [
          { label: "Status", value: IDEA_STATUS_LABELS[idea.status], tone: "", explain: "" },
          {
            label: "Triggered",
            value: String(idea.criteria_counts?.triggered ?? 0),
            tone: (idea.criteria_counts?.triggered ?? 0) > 0 ? "warning" : "",
            explain: "state.triggered",
          },
          {
            label: "Review",
            value: daysToReviewText(ideaReviewDays),
            tone: ideaReviewDays != null && ideaReviewDays < 0 ? "warning" : "",
            explain: "stat.days_to_review",
          },
          { label: "Supports", value: String(idea.evidence_counts.supports), tone: "", explain: "stat.evidence_balance" },
          { label: "Challenges", value: String(idea.evidence_counts.challenges), tone: "", explain: "" },
          { label: "Context", value: String(idea.evidence_counts.context), tone: "", explain: "" },
        ]
      : [
          { label: "Draft", value: String(statusCounts.draft ?? 0), tone: "", explain: "" },
          { label: "Active", value: String(statusCounts.active ?? 0), tone: "", explain: "" },
          { label: "New triggers", value: String(totalTriggered), tone: totalTriggered > 0 ? "warning" : "", explain: "" },
          { label: "Archived", value: String(statusCounts.archived ?? 0), tone: "", explain: "" },
          { label: "Pins", value: String(totalPins), tone: "", explain: "" },
        ];

  function rowLegs(row: IdeaSummary) {
    return formatLegs(row.legs);
  }
</script>

<section class="ideas-view">
  <article class="panel header-panel">
    <div class="header-top">
      <span class="title">Ideas</span>
      <span class="subtitle">{mode === "idea" && idea ? idea.title : mode === "review" ? "Closed ideas · your own record" : boardSubtitle()}</span>
    </div>
    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Ideas modes">
        {#each modes as option}
          <button
            class="mode-btn"
            type="button"
            role="tab"
            class:selected={mode === option.id}
            aria-selected={mode === option.id}
            on:click={() => (mode = option.id)}>{option.label}</button
          >
        {/each}
      </div>
      <div class="header-kpis">
        {#each headerKpis as kpi}
          <div class="header-kpi">
            <span>{kpi.label}{#if kpi.explain && idea}<WhatIsThis key={kpi.explain} stance={idea.stance} />{/if}</span>
            <strong class={kpi.tone}>{kpi.value}</strong>
          </div>
        {/each}
      </div>
    </div>
  </article>

  {#if errorMessage}
    <p class="ideas-error" role="alert">{errorMessage}</p>
  {/if}

  {#if mode === "board"}
    <article class="panel is-flush board-panel">
      <div class="panel-title board-toolbar">
        <div class="toolbar-group">
          <div class="segmented" role="group" aria-label="Filter ideas by status">
            {#each IDEA_BOARD_FILTERS as option}
              <button type="button" class:selected={filter === option.id} aria-pressed={filter === option.id} on:click={() => (filter = option.id)}
                >{option.label}</button
              >
            {/each}
          </div>
          <select class="form-control is-small tag-filter" bind:value={tagFilter} aria-label="Filter ideas by tag" disabled={!list?.tags.length}>
            <option value="">{list?.tags.length ? "All tags" : "No tags"}</option>
            {#each list?.tags ?? [] as tag}
              <option value={tag}>{tag}</option>
            {/each}
          </select>
        </div>
        <div class="toolbar-group">
          <span class="header-meta">{boardRows.length} shown</span>
          <button type="button" class="btn is-small is-primary" aria-expanded={createOpen} on:click={() => (createOpen = !createOpen)}>New idea</button>
        </div>
      </div>

      {#if createOpen}
        <form class="create-row" on:submit|preventDefault={submitCreate}>
          <input class="form-control is-small create-title" bind:value={createTitle} maxlength="200" placeholder="One-line idea" aria-label="New idea title" />
          <select class="form-control is-small" bind:value={createStance} aria-label="New idea stance">
            {#each IDEA_STANCES as option}
              <option value={option}>{IDEA_STANCE_LABELS[option]}</option>
            {/each}
          </select>
          <button type="button" class="btn is-small is-ghost" on:click={() => (createOpen = false)}>Cancel</button>
          <button type="submit" class="btn is-small is-primary" disabled={!createTitle.trim() || creating}>{creating ? "Creating…" : "Create"}</button>
        </form>
      {/if}

      <div class="table-scroll">
        <table class="data-table is-sticky board-table">
          <thead>
            <tr>
              <th>Idea</th>
              <th>Stance</th>
              <th>Legs</th>
              <th>Status</th>
              <th>Criteria</th>
              <th class="num" title={`${TRACKING_LABEL}: net return since activation, after costs`}>Since activation <span class="hyp">(hyp.)</span></th>
              <th class="num">Review</th>
              <th class="num">Supports</th>
              <th class="num">Challenges</th>
              <th class="num">Context</th>
              <th class="num">Last pin</th>
            </tr>
          </thead>
          <tbody>
            {#each boardRows as row (row.idea_id)}
              {@const trackingCell = boardTrackingCell(row)}
              <tr
                class="board-row"
                tabindex="0"
                on:click={() => onOpenIdea(row.idea_id)}
                on:keydown={(event) => activateRowOnKey(event, () => onOpenIdea(row.idea_id))}
              >
                <td class="idea-cell">
                  <strong>{row.title}</strong>
                  <span class="meta" class:muted={!row.thesis}
                    >{row.thesis || "No thesis yet"}{#if row.tags.length}<span class="row-tags"> · {row.tags.join(", ")}</span>{/if}</span
                  >
                </td>
                <td><span class="tag">{IDEA_STANCE_LABELS[row.stance]}</span></td>
                <td class="legs-cell" class:absent={!row.legs.length}>{rowLegs(row)}</td>
                <td><span class="tag {ideaStatusTone(row.status)}">{IDEA_STATUS_LABELS[row.status]}</span></td>
                <td class="criteria-cell" class:absent={!row.criteria_total}>
                  {#if row.criteria_total}
                    {#each criteriaSummary(row.criteria_counts) as item}
                      <span class="tag" class:warning={item.state === "triggered" || item.state === "unavailable" || item.state === "stale"}
                        >{item.count} {CRITERION_STATE_LABELS[item.state].toLowerCase()}</span
                      >
                    {/each}
                  {:else}
                    None
                  {/if}
                </td>
                <td class="num tracking-cell" class:absent={trackingCell.absent} title={trackingCell.title}>
                  <span class={trackingCell.tone}>{trackingCell.text}</span>
                  {#if trackingCell.meta}<span class="meta">{trackingCell.meta}</span>{/if}
                </td>
                <td class="num" class:absent={!row.review_date} class:warning={(daysToReview(row.review_date) ?? 1) < 0}>{daysToReviewText(daysToReview(row.review_date))}</td>
                <td class="num" class:absent={!row.evidence_counts.supports}>{row.evidence_counts.supports}</td>
                <td class="num" class:absent={!row.evidence_counts.challenges}>{row.evidence_counts.challenges}</td>
                <td class="num" class:absent={!row.evidence_counts.context}>{row.evidence_counts.context}</td>
                <td class="num" class:absent={!row.last_evidence_at}>{row.last_evidence_at ? formatIdeaInstant(row.last_evidence_at) : "No pins"}</td>
              </tr>
            {:else}
              <tr class="empty-row">
                <td colspan="11">
                  {#if loading && !list}
                    Loading…
                  {:else if summaries.length}
                    No ideas match this filter.
                  {:else}
                    No ideas yet. Create one here, promote a Sitrep follow-up, or use Pin to idea on any panel with a source badge.
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      {#if storageWarnings.length}
        <ul class="storage-warnings">
          {#each storageWarnings as warning}
            <li><span class="tag warning">Storage</span> {warning.message}</li>
          {/each}
        </ul>
      {/if}
    </article>
  {:else if mode === "review"}
    <IdeaReviewMode stats={reviewStats} loading={loading} {onOpenIdea} />
  {:else if !idea}
    <article class="panel idea-empty">
      <p>{loading ? "Loading…" : "No idea selected. Open one from the Board, or create one there."}</p>
      <button type="button" class="btn is-small is-ghost" on:click={() => (mode = "board")}>Open the Board</button>
    </article>
  {:else}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel is-flush thesis-panel">
          <div class="panel-title thesis-title">
            <h3>Thesis</h3>
            <div class="title-actions">
              {#if !editing}
                <button type="button" class="btn is-small is-ghost" on:click={startEdit}>Edit</button>
                {#if idea.status === "draft"}
                  <button
                    type="button"
                    class="btn is-small is-primary"
                    disabled={!idea.thesis}
                    title={idea.thesis ? "Mark the idea active" : "Write the thesis before activating"}
                    on:click={() => idea && onTransition(idea.idea_id, "activate")}>Activate</button
                  >
                {/if}
                {#if idea.status === "active"}
                  <button type="button" class="btn is-small is-ghost" aria-expanded={closing} on:click={() => (closing = !closing)}>Close</button>
                {:else if idea.status === "closed"}
                  <button
                    type="button"
                    class="btn is-small is-ghost"
                    title="Reopen as active; the review stays in the record"
                    on:click={() => idea && onTransition(idea.idea_id, "reopen")}>Reopen</button
                  >
                {/if}
                {#if idea.status === "draft" || idea.status === "active" || idea.status === "closed"}
                  <button type="button" class="btn is-small is-ghost" on:click={() => idea && onTransition(idea.idea_id, "archive")}>Archive</button>
                {:else if idea.status === "archived"}
                  <button type="button" class="btn is-small is-ghost" on:click={() => idea && onTransition(idea.idea_id, "restore")}>Restore</button>
                {/if}
                <button type="button" class="btn is-small is-ghost" on:click={() => download("md")}>Export Markdown</button>
                <button type="button" class="btn is-small is-ghost" on:click={() => download("json")}>Export JSON</button>
                {#if confirmDelete}
                  <button type="button" class="btn is-small is-ghost" on:click={() => (confirmDelete = false)}>Keep</button>
                {/if}
                <button type="button" class="btn is-small is-danger" on:click={removeIdea}>{confirmDelete ? "Confirm delete" : "Delete"}</button>
              {/if}
            </div>
          </div>

          <div class="thesis-body">
            {#if exportError}<p class="ideas-error" role="alert">{exportError}</p>{/if}
            {#if editing}
              <form class="idea-form" on:submit|preventDefault={saveEdit}>
                <label class="field wide"><span>Title</span><input class="form-control" bind:value={formTitle} maxlength="200" /></label>
                <label class="field wide"
                  ><span>Thesis</span><textarea class="form-control" rows="2" bind:value={formThesis} maxlength="1000" placeholder="I think X because Y"></textarea></label
                >
                <div class="field wide">
                  <span id="idea-stance-label">Stance</span>
                  <div class="segmented" role="radiogroup" aria-labelledby="idea-stance-label">
                    {#each IDEA_STANCES as option}
                      <button type="button" role="radio" aria-checked={formStance === option} class:selected={formStance === option} on:click={() => (formStance = option)}
                        >{IDEA_STANCE_LABELS[option]}</button
                      >
                    {/each}
                  </div>
                </div>
                <div class="field wide">
                  <span>Legs</span>
                  <table class="data-table is-compact legs-editor">
                    <thead><tr><th>Label</th><th>Id</th><th>Type</th><th class="num">Weight</th><th><span class="sr-only">Remove</span></th></tr></thead>
                    <tbody>
                      {#each formLegs as row, index}
                        <tr>
                          <td><input class="form-control is-small" bind:value={row.label} aria-label="Leg label" /></td>
                          <td><input class="form-control is-small" bind:value={row.normalized_id} aria-label="Leg id" placeholder="XOM" /></td>
                          <td>
                            <select class="form-control is-small" bind:value={row.entity_type} aria-label="Leg type">
                              {#each ["equity", "etf", "commodity", "crypto", "prediction_market", "fx", "rates", "macro", "other"] as type}
                                <option value={type}>{type.replace(/_/g, " ")}</option>
                              {/each}
                            </select>
                          </td>
                          <td class="num"
                            ><input class="form-control is-small weight-input" bind:value={row.weight} inputmode="decimal" aria-label="Signed weight" placeholder="+1" /></td
                          >
                          <td><button type="button" class="btn is-small is-ghost" on:click={() => removeLegRow(index)} aria-label="Remove leg">Remove</button></td>
                        </tr>
                        {#if legErrors[index]}<tr class="leg-error"><td colspan="5">{legErrors[index]}</td></tr>{/if}
                      {:else}
                        <tr class="empty-row"><td colspan="5">No legs. A pure event idea needs none.</td></tr>
                      {/each}
                    </tbody>
                  </table>
                  <div><button type="button" class="btn is-small is-ghost" on:click={addLegRow}>Add leg</button></div>
                </div>
                <label class="field"><span>Review date</span><input class="form-control" type="date" bind:value={formReviewDate} /></label>
                <label class="field"><span>Holding window</span><input class="form-control" bind:value={formWindow} maxlength="80" placeholder="3M" /></label>
                <label class="field wide"><span>Tags</span><input class="form-control" bind:value={formTags} placeholder="energy, refiners" /></label>
                <label class="field wide"><span>Notes</span><textarea class="form-control" rows="6" bind:value={formNotes} maxlength="20000"></textarea></label>
                <div class="form-actions wide">
                  <button type="button" class="btn is-ghost" on:click={() => (editing = false)}>Cancel</button>
                  <button type="submit" class="btn is-primary" disabled={!canSave}>{saving ? "Saving…" : "Save"}</button>
                </div>
              </form>
            {:else}
              <p class="thesis-text" class:muted={!idea.thesis}>{idea.thesis || "No thesis yet. Edit the idea to write one before activating it."}</p>
              <table class="data-table is-keyvalue is-compact idea-facts">
                <tbody>
                  <tr><th>Stance</th><td>{IDEA_STANCE_LABELS[idea.stance]}</td></tr>
                  <tr><th>Status</th><td><span class="tag {ideaStatusTone(idea.status)}">{IDEA_STATUS_LABELS[idea.status]}</span></td></tr>
                  <tr><th>Legs</th><td class:absent={!idea.legs.length}>{formatLegs(idea.legs.map((leg) => ({ label: leg.entity.label, weight: leg.weight })))}</td></tr>
                  <tr><th>Horizon</th><td class:absent={!idea.horizon.review_date && !idea.horizon.holding_window}>{horizonText(idea)}</td></tr>
                  <tr><th>Tags</th><td class:absent={!idea.tags.length}>{idea.tags.join(", ") || "None"}</td></tr>
                  <tr>
                    <th>Origin</th>
                    <td>
                      <div class="origin-cell">
                      <span>{idea.origin.kind === "sitrep_follow_up" ? "Sitrep follow-up" : idea.origin.kind === "manual" ? "Manual" : idea.origin.kind}{idea.origin.label ? ` · ${idea.origin.label}` : ""}</span>
                      {#if idea.origin.handoff}
                        <button type="button" class="btn is-small is-ghost" title={`Open ${handoffPlaceLabel(idea.origin.handoff, "target")}`} on:click={() => idea?.origin.handoff && onReopen(idea.origin.handoff)}>Reopen</button>
                      {/if}
                      </div>
                    </td>
                  </tr>
                  <tr><th>Updated</th><td>{formatIdeaInstant(idea.updated_at)} · created {formatIdeaInstant(idea.created_at)}</td></tr>
                </tbody>
              </table>
              {#if idea.notes}
                <div class="notes-text">{idea.notes}</div>
              {/if}
            {/if}
          </div>
        </article>

        {#if closing && idea.status === "active"}
          <IdeaCloseForm {idea} {tracking} {trackingLoading} {trackingError} onSubmit={submitClose} onCancel={() => (closing = false)} />
        {/if}
        <IdeaReviewSection {idea} {tracking} />

        {#each IDEA_EVIDENCE_STANCES as stance}
          <article class="panel is-flush evidence-panel" data-stance={stance}>
            <div class="panel-title">
              <h3>{EVIDENCE_STANCE_LABELS[stance]}</h3>
              <span class="header-meta">{groups[stance].length} {groups[stance].length === 1 ? "pin" : "pins"}</span>
            </div>
            <div class="table-scroll">
              <table class="data-table is-top evidence-table">
                <colgroup>
                  <col class="col-evidence" />
                  <col class="col-values" />
                  <col class="col-source" />
                  <col class="col-captured" />
                  <col class="col-actions" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Evidence</th>
                    <th>Captured values</th>
                    <th>Source</th>
                    <th class="num">Captured</th>
                    <th><span class="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {#each groups[stance] as pin (pin.evidence_id)}
                    <tr>
                      <td class="evidence-cell">
                        <strong>{pin.title}</strong>
                        <span class="meta">{handoffPlaceLabel(pin.reopen) || pin.kind.replace(/_/g, " ")}{pin.reopen?.selected_entity ? ` · ${pin.reopen.selected_entity.label}` : ""}{pin.reopen?.selected_timeframe ? ` · ${pin.reopen.selected_timeframe.label}` : ""}</span>
                        {#if pin.note}<span class="meta pin-note">{pin.note}</span>{/if}
                      </td>
                      <td class="values-cell">
                        {#if capturedMetricPairs(pin.captured_values).length}
                          {@const expanded = expandedPins.includes(pin.evidence_id)}
                          {@const limit = expanded ? 500 : 6}
                          <dl class="value-pairs">
                            {#each capturedMetricPairs(pin.captured_values, limit) as pair}
                              <div><dt>{pair.label}</dt><dd>{pair.display}</dd></div>
                            {/each}
                          </dl>
                          {#if capturedValuesExtraCount(pin.captured_values) || expanded}
                            <button type="button" class="more-link" aria-expanded={expanded} on:click={() => toggleExpanded(pin.evidence_id)}
                              >{expanded ? "Show fewer" : `+${capturedValuesExtraCount(pin.captured_values)} more`}</button
                            >
                          {/if}
                        {:else if pin.captured_values.text}
                          <span class="captured-text">{pin.captured_values.text}</span>
                        {:else if pin.captured_values.table}
                          <span class="meta">{pin.captured_values.table.rows.length} rows × {pin.captured_values.table.columns.length} columns</span>
                        {:else}
                          <span class="absent">No values captured</span>
                        {/if}
                      </td>
                      <td class="source-cell">
                        <ProvenanceBadge data={pinBadgeData(pin) ? toProvenanceBadge(pinBadgeData(pin)) : null} showTime={false} />
                      </td>
                      <td class="num captured-cell">{formatIdeaInstant(pin.captured_at)}</td>
                      <td class="actions-cell">
                        <button type="button" class="btn is-small is-ghost" disabled={!pin.reopen} title={reopenTitle(pin)} on:click={() => pin.reopen && onReopen(pin.reopen)}>Reopen</button>
                        <button type="button" class="btn is-small" class:is-danger={confirmUnpin === pin.evidence_id} class:is-ghost={confirmUnpin !== pin.evidence_id} on:click={() => unpin(pin)}
                          >{confirmUnpin === pin.evidence_id ? "Confirm unpin" : "Unpin"}</button
                        >
                      </td>
                    </tr>
                  {:else}
                    <tr class="empty-row"><td colspan="5">{stanceEmpty(stance)}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </article>
        {/each}

        <IdeaCriteriaPanel
          {idea}
          registry={observables}
          busy={criteriaBusy}
          onLoadRegistry={onLoadObservables}
          onSave={(criterionId, payload) => (idea ? onSaveCriterion(idea.idea_id, criterionId, payload) : Promise.resolve(false))}
          onRemove={(criterionId) => (idea ? onRemoveCriterion(idea.idea_id, criterionId) : Promise.resolve(null))}
          onAcknowledge={(criterionId) => (idea ? onAcknowledgeCriterion(idea.idea_id, criterionId) : Promise.resolve(null))}
          onEvaluate={() => (idea ? onEvaluateIdea(idea.idea_id) : Promise.resolve(null))}
          onPreview={onPreviewObservable}
          {onLoadEvents}
        />

        <IdeaAnalysisPanel {idea} busy={analysisBusy} error={analysisError} {onRunTest} {onRunRisk} />

        <IdeaTrackingPanel
          {idea}
          {tracking}
          loading={trackingLoading}
          error={trackingError}
          onLoad={onLoadTracking}
          onUpdate={onUpdateTracking}
        />
      </div>

      <div class="support-column">
        <article class="panel is-flush journal-panel">
          <div class="panel-title">
            <h3>Journal</h3>
            <span class="header-meta">{idea.journal.length} {idea.journal.length === 1 ? "entry" : "entries"} · append-only</span>
          </div>
          <form class="journal-form" on:submit|preventDefault={submitJournal}>
            <div class="segmented" role="radiogroup" aria-label="Journal entry kind">
              <button type="button" role="radio" aria-checked={journalKind === "note"} class:selected={journalKind === "note"} on:click={() => (journalKind = "note")}>Note</button>
              <button type="button" role="radio" aria-checked={journalKind === "decision"} class:selected={journalKind === "decision"} on:click={() => (journalKind = "decision")}>Decision</button>
            </div>
            <textarea class="form-control" rows="2" bind:value={journalBody} maxlength="4000" placeholder="What changed, what you decided" aria-label="Journal entry"></textarea>
            <div class="form-actions">
              <button type="submit" class="btn is-small is-primary" disabled={!journalBody.trim() || journalSaving}>{journalSaving ? "Adding…" : "Add entry"}</button>
            </div>
          </form>
          <table class="data-table is-compact is-top journal-table">
            <thead><tr><th>Time</th><th>Entry</th></tr></thead>
            <tbody>
              {#each journalNewestFirst as entry (entry.entry_id)}
                <tr>
                  <td class="num journal-time">{formatIdeaInstant(entry.created_at)}</td>
                  <td>
                    <span class="journal-kind" class:is-user={entry.author === "user"}>{journalKindLabel(entry.kind)}</span>
                    <span class="journal-body">{entry.body}</span>
                    {#each entryDetail(entry) as detail}
                      <span class="meta">{detail}</span>
                    {/each}
                  </td>
                </tr>
              {:else}
                <tr class="empty-row"><td colspan="2">No entries.</td></tr>
              {/each}
            </tbody>
          </table>
        </article>
      </div>
    </div>
  {/if}
</section>

<style>
  /* One column that may shrink below its content, so a wide table scrolls
     inside its sheet instead of widening the page on a narrow window. */
  .ideas-view {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
    min-width: 0;
  }

  .ideas-error {
    margin: 0;
    color: var(--negative);
    font-size: var(--text-sm);
  }

  /* ── Board ── */
  .board-toolbar {
    flex-wrap: wrap;
    padding-block: var(--space-3);
  }

  .toolbar-group {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
    min-width: 0;
  }

  .tag-filter {
    min-width: 8rem;
    font-weight: 400;
  }

  .create-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    padding: 0 var(--space-5) var(--space-4);
  }

  .create-title {
    flex: 1 1 18rem;
    min-width: 0;
  }

  /* Positioned, so the visually hidden header labels stay inside the scroll
     box instead of widening the page on a narrow window. */
  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .board-row {
    cursor: pointer;
  }

  .board-row:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .idea-cell {
    min-width: 16rem;
    max-width: 34rem;
  }

  .idea-cell strong {
    font-family: var(--font-ui);
  }

  .idea-cell .meta {
    white-space: normal;
  }

  .muted {
    color: var(--text-2);
  }

  .row-tags {
    color: var(--text-2);
  }

  .legs-cell {
    min-width: 7rem;
  }

  .criteria-cell {
    min-width: 8rem;
  }

  /* I3a: rentabilidad hipotética desde la activación, con su sesión as of debajo. */
  .tracking-cell {
    min-width: 7.5rem;
    white-space: nowrap;
  }

  .tracking-cell > span:first-child {
    display: block;
  }

  .tracking-cell .positive {
    color: var(--positive);
  }

  .tracking-cell .negative {
    color: var(--negative);
  }

  .hyp {
    color: var(--text-2);
    font-weight: 400;
  }

  .criteria-cell .tag + .tag {
    margin-left: var(--space-1);
  }

  td.warning,
  .header-kpi strong.warning {
    color: var(--warning);
  }

  .header-kpi span {
    display: inline-flex;
    align-items: center;
  }

  .storage-warnings {
    display: grid;
    gap: var(--space-2);
    margin: 0;
    padding: var(--space-3) var(--space-5) var(--space-4);
    list-style: none;
    font-size: var(--text-sm);
    color: var(--text-1);
    overflow-wrap: anywhere;
  }

  /* ── Idea ── */
  .idea-empty {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    flex-wrap: wrap;
  }

  .idea-empty p {
    margin: 0;
    color: var(--text-1);
  }

  .thesis-title {
    flex-wrap: wrap;
    padding-block: var(--space-3);
  }

  .title-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-2);
  }

  .thesis-body {
    display: grid;
    gap: var(--space-4);
    padding: 0 var(--space-5) var(--space-5);
  }

  .thesis-text {
    margin: 0;
    color: var(--text-0);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
  }

  .thesis-text.muted {
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  /* The key/value table sits inside the padded body, so its outer columns
     drop the 12px sheet inset the flush-table rule gives them. */
  .idea-facts th:first-child,
  .idea-facts td:first-child {
    padding-left: 0;
  }

  .idea-facts td:last-child {
    padding-right: 0;
  }

  .origin-cell {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .notes-text {
    white-space: pre-wrap;
    color: var(--text-1);
    font-size: var(--text-sm);
    line-height: var(--leading-normal);
  }

  .idea-form {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .field {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .field > span {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .wide {
    grid-column: 1 / -1;
  }

  .legs-editor th:first-child,
  .legs-editor td:first-child {
    padding-left: 0;
  }

  .legs-editor input,
  .legs-editor select {
    width: 100%;
    min-width: 5rem;
  }

  .weight-input {
    text-align: right;
  }

  .leg-error td {
    color: var(--negative);
    font-size: var(--text-xs);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  /* The three stance tables share one column grid, so supports, challenges
     and context line up for comparison; a narrow window scrolls them. */
  .evidence-table {
    table-layout: fixed;
    min-width: 46rem;
  }

  .col-evidence { width: 24%; }
  .col-values { width: 30%; }
  .col-source { width: 24%; }
  .col-captured { width: 10rem; }
  .col-actions { width: 10.5rem; }

  .evidence-cell {
    overflow-wrap: anywhere;
  }

  .more-link {
    padding: 0;
    border: 0;
    background: none;
    color: var(--accent);
    font-family: var(--font-ui);
    font-size: var(--text-2xs);
    cursor: pointer;
  }

  .more-link:hover {
    text-decoration: underline;
  }

  .evidence-cell strong {
    font-family: var(--font-ui);
  }

  .evidence-cell .meta {
    white-space: normal;
  }

  .pin-note {
    color: var(--text-1);
  }

  .values-cell {
    min-width: 0;
  }

  .value-pairs {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-5);
    margin: 0;
  }

  .value-pairs div {
    display: flex;
    gap: var(--space-2);
    align-items: baseline;
  }

  .value-pairs dt {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
  }

  .value-pairs dd {
    margin: 0;
    color: var(--text-0);
    font-family: var(--font-num);
    white-space: nowrap;
  }

  .captured-text {
    white-space: normal;
  }

  .source-cell {
    white-space: nowrap;
  }

  .captured-cell {
    white-space: nowrap;
  }

  .actions-cell {
    white-space: nowrap;
    text-align: right;
  }

  .actions-cell .btn + .btn {
    margin-left: var(--space-2);
  }

  .journal-form {
    display: grid;
    gap: var(--space-3);
    padding: 0 var(--space-5) var(--space-4);
  }

  .journal-time {
    white-space: nowrap;
    color: var(--text-2);
    text-align: left;
  }

  .journal-kind {
    display: inline-block;
    margin-right: var(--space-2);
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .journal-kind.is-user {
    color: var(--accent);
  }

  .journal-body {
    font-family: var(--font-ui);
    white-space: pre-wrap;
  }

  .journal-table .meta {
    white-space: normal;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  @media (max-width: 720px) {
    .idea-form {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
