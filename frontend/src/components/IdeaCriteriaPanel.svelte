<script lang="ts">
  // Criteria section of the Idea view (Workstream 12, I2): rules stated before
  // the outcome is known, with their live state. The backend evaluates them
  // through read-only observables; this panel only edits rules and shows what
  // the last evaluation found. Unavailable is never shown as holding.
  import type {
    Idea,
    IdeaCriterion,
    IdeaCriterionCadence,
    IdeaCriterionCondition,
    IdeaCriterionKind,
    IdeaCriterionPayload,
    IdeaCriterionWindow,
    IdeaObservableDefinition,
    IdeaObservablePreview,
    IdeaObservableRef,
    IdeaObservableRegistryResponse,
  } from "../lib/api/types";
  import {
    CADENCE_LABELS,
    CONDITION_LABELS,
    CRITERION_KINDS,
    CRITERION_KIND_LABELS,
    CRITERION_STATE_LABELS,
    CRITERION_WINDOWS,
    criteriaSummary,
    criterionArmedText,
    criterionNowText,
    criterionStateTone,
    defaultObservableLabel,
    describeCriterion,
    formatObservableValue,
    groupObservables,
    needsThreshold,
    observableChangeUnit,
    observableValueUnit,
    paramsComplete,
    shortDate,
  } from "../lib/idea-criteria";
  import { formatIdeaInstant } from "../lib/ideas";
  import { toProvenanceBadge } from "../lib/provenance";
  import ProvenanceBadge from "./ProvenanceBadge.svelte";
  import WhatIsThis from "./WhatIsThis.svelte";

  export let idea: Idea;
  export let registry: IdeaObservableRegistryResponse | null = null;
  export let busy = false;
  export let onLoadRegistry: () => void | Promise<unknown> = () => {};
  export let onSave: (criterionId: string | null, payload: IdeaCriterionPayload) => Promise<boolean> = async () => false;
  export let onRemove: (criterionId: string) => Promise<unknown> = async () => null;
  export let onAcknowledge: (criterionId: string) => Promise<unknown> = async () => null;
  export let onEvaluate: () => Promise<unknown> = async () => null;
  export let onPreview: (observable: IdeaObservableRef) => Promise<IdeaObservablePreview | null> = async () => null;
  export let onLoadEvents: () => Promise<Array<{ event_id: string; title: string; scheduled_at: string; region: string }>> = async () => [];

  // ── Form state ──────────────────────────────────────────────────────────
  let formOpen = false;
  let editingId: string | null = null;
  let kind: IdeaCriterionKind = "invalidate";
  let observableId = "";
  let params: Record<string, string> = {};
  let observableLabel = "";
  let condition: IdeaCriterionCondition = "below";
  let thresholdText = "";
  let windowId: IdeaCriterionWindow = "1m";
  let cadence: IdeaCriterionCadence = "daily_close";
  let labelText = "";
  let labelTouched = false;
  let saving = false;
  let formError = "";
  let preview: IdeaObservablePreview | null = null;
  let previewing = false;
  let confirmRemove: string | null = null;
  let events: Array<{ event_id: string; title: string; scheduled_at: string; region: string }> = [];
  let eventsLoading = false;
  let lastIdeaId = idea.idea_id;
  const formId = `criterion-${Math.random().toString(36).slice(2, 9)}`;

  $: if (idea.idea_id !== lastIdeaId) {
    lastIdeaId = idea.idea_id;
    formOpen = false;
    confirmRemove = null;
  }

  $: definitions = registry?.items ?? [];
  $: groups = groupObservables(definitions);
  $: definition = definitions.find((item) => item.observable_id === observableId) ?? null;
  $: ref = { observable_id: observableId, params: cleanParams(params), label: observableLabel || defaultObservableLabel(definition, params) };
  $: valueUnit = observableValueUnit(definition, ref);
  $: changeUnit = observableChangeUnit(definition, ref);
  $: thresholdValue = thresholdText.trim() === "" ? null : Number(thresholdText);
  $: thresholdValid = !needsThreshold(condition) || (thresholdValue != null && Number.isFinite(thresholdValue) && (condition !== "change_over_window" || thresholdValue !== 0));
  $: generatedLabel = definition
    ? describeCriterion({
        observableLabel: ref.label,
        condition,
        threshold: needsThreshold(condition) ? thresholdValue : null,
        window: condition === "change_over_window" ? windowId : null,
        changeUnit,
        formatThreshold: (value) => formatObservableValue(valueUnit, value),
      })
    : "";
  $: if (!labelTouched) labelText = generatedLabel;
  $: complete = Boolean(definition) && paramsComplete(definition, params) && thresholdValid;
  $: saveHint = !definition ? "Choose what to watch" : !paramsComplete(definition, params) ? "Fill in what the observable needs" : !thresholdValid ? "Enter a threshold" : "";
  $: counts = criteriaSummary(idea.criteria_counts);
  $: suggestions = buildSuggestions(idea);
  $: evaluable = idea.status === "active";

  function cleanParams(raw: Record<string, string>): Record<string, string> {
    return Object.fromEntries(Object.entries(raw).filter(([, value]) => String(value ?? "").trim() !== ""));
  }

  /** Tickers and contracts the idea already names (legs and pins), with the titles the pins carry. */
  function buildSuggestions(current: Idea) {
    const tickers = new Set<string>();
    const contracts = new Map<string, string>();
    for (const leg of current.legs) {
      if (["equity", "etf"].includes(leg.entity.entity_type)) tickers.add(leg.entity.normalized_id);
    }
    for (const pin of current.evidence) {
      const entity = pin.reopen?.selected_entity;
      const ids = pin.reopen?.normalized_ids ?? {};
      if (pin.kind === "prediction_contract" || pin.reopen?.source_tab === "prediction_markets") {
        const marketId = ids.market_id ?? entity?.normalized_id;
        if (marketId && marketId.includes(":")) contracts.set(marketId, entity?.label || pin.title);
      } else if (entity && ["equity", "etf"].includes(entity.entity_type)) {
        tickers.add(entity.normalized_id);
      } else if (ids.symbol) {
        tickers.add(ids.symbol);
      }
    }
    return {
      tickers: [...tickers].slice(0, 20),
      contracts: [...contracts.keys()].slice(0, 20),
      contractTitles: Object.fromEntries(contracts) as Record<string, string>,
    };
  }

  /** A contract chosen from the idea's own pins is labelled by its title, not its id. */
  function contractLabel(marketId: string): string {
    const title = suggestions.contractTitles[marketId.trim()];
    return title ? `${title.length > 90 ? `${title.slice(0, 89)}…` : title} probability` : "";
  }

  async function openForm(criterion: IdeaCriterion | null = null) {
    if (!registry) await onLoadRegistry();
    formError = "";
    preview = null;
    confirmRemove = null;
    if (criterion) {
      editingId = criterion.criterion_id;
      kind = criterion.kind;
      observableId = criterion.observable.observable_id;
      params = { ...criterion.observable.params };
      observableLabel = criterion.observable.label;
      condition = criterion.condition;
      thresholdText = criterion.threshold == null ? "" : String(criterion.threshold);
      windowId = criterion.window ?? "1m";
      cadence = criterion.cadence;
      labelText = criterion.label;
      labelTouched = true;
    } else {
      editingId = null;
      kind = "invalidate";
      observableId = "";
      params = {};
      observableLabel = "";
      thresholdText = "";
      windowId = "1m";
      labelTouched = false;
      selectObservable(groups[0]?.items[0]?.observable_id ?? "");
    }
    formOpen = true;
  }

  function selectObservable(id: string) {
    observableId = id;
    const next = definitions.find((item) => item.observable_id === id) ?? null;
    params = {};
    observableLabel = "";
    preview = null;
    if (next) {
      if (!next.conditions.includes(condition)) condition = next.conditions[0];
      if (!next.cadences.includes(cadence)) cadence = next.cadences.includes("daily_close") ? "daily_close" : next.cadences[0];
      if (next.observable_id === "macro_event") void loadEvents();
      const tickerParam = next.params.find((param) => param.kind === "ticker");
      if (tickerParam && suggestions.tickers.length) params = { [tickerParam.name]: suggestions.tickers[0] };
      const contractParam = next.params.find((param) => param.kind === "contract");
      if (contractParam && suggestions.contracts.length) {
        params = { [contractParam.name]: suggestions.contracts[0] };
        observableLabel = contractLabel(suggestions.contracts[0]);
      }
    }
  }

  async function loadEvents() {
    if (events.length || eventsLoading) return;
    eventsLoading = true;
    try {
      events = await onLoadEvents();
    } finally {
      eventsLoading = false;
    }
  }

  function chooseEvent(eventId: string) {
    const match = events.find((item) => item.event_id === eventId);
    params = match
      ? { event_id: match.event_id, title: match.title, scheduled_at: match.scheduled_at, region: match.region }
      : {};
    observableLabel = match?.title ?? "";
  }

  function setParam(name: string, value: string) {
    params = { ...params, [name]: value };
    preview = null;
    if (definition?.params.find((param) => param.name === name)?.kind === "contract") observableLabel = contractLabel(value);
  }

  async function checkNow() {
    if (!definition || !paramsComplete(definition, params)) return;
    previewing = true;
    try {
      preview = await onPreview(ref);
    } finally {
      previewing = false;
    }
  }

  async function save() {
    if (!complete || saving) return;
    saving = true;
    formError = "";
    try {
      const payload: IdeaCriterionPayload = {
        kind,
        observable: ref,
        condition,
        threshold: needsThreshold(condition) ? thresholdValue : null,
        window: condition === "change_over_window" ? windowId : null,
        cadence,
        // An untouched label is left to the server, which generates it from the rule.
        label: labelTouched && labelText.trim() ? labelText.trim() : null,
      };
      const ok = await onSave(editingId, payload);
      if (ok) formOpen = false;
      else formError = "The criterion could not be saved.";
    } finally {
      saving = false;
    }
  }

  async function remove(criterion: IdeaCriterion) {
    if (confirmRemove !== criterion.criterion_id) {
      confirmRemove = criterion.criterion_id;
      return;
    }
    confirmRemove = null;
    await onRemove(criterion.criterion_id);
  }

  function observableName(item: IdeaObservableDefinition): string {
    if (!item.available) return `${item.label} · ${item.needs_tws ? "needs Trader Workstation" : "unavailable"}`;
    return item.needs_tws ? `${item.label} · needs Trader Workstation` : item.label;
  }

  function definitionFor(criterion: IdeaCriterion) {
    return definitions.find((item) => item.observable_id === criterion.observable.observable_id) ?? null;
  }

  function thresholdUnitHint(): string {
    if (condition === "change_over_window") return changeUnit === "percent" ? "%, signed: −10 is a fall" : "pts, signed: −10 is a fall";
    if (valueUnit === "probability" || valueUnit === "percent") return "%";
    if (valueUnit === "bp") return "bp";
    if (valueUnit === "usd") return "USD";
    if (valueUnit === "points") return "vol pts";
    return "";
  }

  /** "Detected" with the time only when it is the same day the condition was first met. */
  function detectedText(criterion: IdeaCriterion): string {
    const detected = formatIdeaInstant(criterion.triggered_at);
    const met = criterion.trigger_evaluation?.first_met_at;
    const sameDay = met && detected.slice(0, 10) === shortDate(met);
    return `Detected ${sameDay ? detected.slice(11) : detected}${criterion.acknowledged_at ? " · acknowledged" : ""}`;
  }

  function previewText(item: IdeaObservablePreview): string {
    if (!item.available) return item.reason ?? "Unavailable";
    if (item.event_time && item.value == null) return `Scheduled ${shortDate(item.event_time)}${item.event_released ? " · released" : ""}`;
    const parts = [item.value_display ?? "N/A"];
    if (item.as_of) parts.push(shortDate(item.as_of));
    if (item.history_points) parts.push(`${item.history_points} observations`);
    return parts.join(" · ");
  }
</script>

<article class="panel is-flush criteria-panel">
  <div class="panel-title criteria-title">
    <h3>Criteria <WhatIsThis key="cadence" stance={idea.stance} /></h3>
    <div class="title-actions">
      {#if counts.length}
        <span class="header-meta">
          {#each counts as item, index}{index ? " · " : ""}{item.count} {CRITERION_STATE_LABELS[item.state].toLowerCase()}{/each}
        </span>
      {/if}
      <button
        type="button"
        class="btn is-small is-ghost"
        disabled={!evaluable || !idea.criteria.length || busy}
        title={evaluable ? "Evaluate every criterion now" : "Only active ideas are evaluated"}
        on:click={() => onEvaluate()}>{busy ? "Evaluating…" : "Evaluate now"}</button
      >
      <button
        type="button"
        class="btn is-small is-ghost"
        aria-expanded={formOpen && !editingId}
        disabled={idea.status !== "draft" && idea.status !== "active"}
        on:click={() => (formOpen && !editingId ? (formOpen = false) : openForm())}>Add criterion</button
      >
    </div>
  </div>

  {#if formOpen}
    <form class="criterion-form" on:submit|preventDefault={save} aria-label={editingId ? "Edit criterion" : "Add criterion"}>
      <div class="field wide">
        <span id={`${formId}-kind`}>Kind</span>
        <div class="kind-row">
          <div class="segmented" role="radiogroup" aria-labelledby={`${formId}-kind`}>
            {#each CRITERION_KINDS as option}
              <button type="button" role="radio" aria-checked={kind === option} class:selected={kind === option} on:click={() => (kind = option)}
                >{CRITERION_KIND_LABELS[option]}</button
              >
            {/each}
          </div>
          <WhatIsThis key={`kind.${kind}`} stance={idea.stance} />
        </div>
      </div>

      <label class="field wide">
        <span>Watch {#if definition}<WhatIsThis key={`observable.${definition.observable_id}`} stance={idea.stance} />{/if}</span>
        <select class="form-control is-small" value={observableId} on:change={(event) => selectObservable(event.currentTarget.value)} aria-label="Observable">
          {#if !definitions.length}<option value="">Loading…</option>{/if}
          {#each groups as group}
            <optgroup label={group.group}>
              {#each group.items as item}
                <option value={item.observable_id}>{observableName(item)}</option>
              {/each}
            </optgroup>
          {/each}
        </select>
        {#if definition}
          <span class="field-note" class:warn={!definition.available}
            >{definition.source}{#if !definition.available} · {definition.unavailable_reason}{:else if definition.dependency_label} · {definition.dependency_label}{/if}</span
          >
        {/if}
      </label>

      {#if definition}
        {#if definition.observable_id === "macro_event"}
          <label class="field wide">
            <span>Event</span>
            <select class="form-control is-small" value={params.event_id ?? ""} on:change={(event) => chooseEvent(event.currentTarget.value)} aria-label="Event">
              <option value="">{eventsLoading ? "Loading…" : events.length ? "Choose an event" : "No upcoming events"}</option>
              {#if params.event_id && !events.some((item) => item.event_id === params.event_id)}
                <option value={params.event_id}>{params.title || params.event_id}</option>
              {/if}
              {#each events as item}
                <option value={item.event_id}>{item.title} · {shortDate(item.scheduled_at)}</option>
              {/each}
            </select>
          </label>
        {:else}
          {#each definition.params as param}
            <label class="field">
              <span>{param.label}{param.required ? "" : " (optional)"}</span>
              {#if param.options.length}
                <select class="form-control is-small" value={params[param.name] ?? ""} on:change={(event) => setParam(param.name, event.currentTarget.value)} aria-label={param.label}>
                  <option value="">Choose…</option>
                  {#each param.options as option}
                    <option value={option.value}>{option.label}</option>
                  {/each}
                </select>
              {:else if param.kind === "date"}
                <input class="form-control is-small" type="date" value={params[param.name] ?? ""} on:input={(event) => setParam(param.name, event.currentTarget.value)} aria-label={param.label} />
              {:else}
                <input
                  class="form-control is-small"
                  value={params[param.name] ?? ""}
                  placeholder={param.placeholder ?? ""}
                  list={param.kind === "ticker" ? `${formId}-tickers` : param.kind === "contract" ? `${formId}-contracts` : undefined}
                  on:input={(event) => setParam(param.name, event.currentTarget.value)}
                  aria-label={param.label}
                />
              {/if}
            </label>
          {/each}
        {/if}

        <label class="field">
          <span>Condition <WhatIsThis key={`condition.${condition}`} stance={idea.stance} /></span>
          <select class="form-control is-small" bind:value={condition} aria-label="Condition">
            {#each definition.conditions as option}
              <option value={option}>{CONDITION_LABELS[option]}</option>
            {/each}
          </select>
        </label>

        {#if needsThreshold(condition)}
          <label class="field">
            <span>Threshold{thresholdUnitHint() ? ` (${thresholdUnitHint()})` : ""}</span>
            <input class="form-control is-small" bind:value={thresholdText} inputmode="decimal" aria-label="Threshold" placeholder={condition === "change_over_window" ? "-10" : "100"} />
          </label>
        {/if}

        {#if condition === "change_over_window"}
          <label class="field">
            <span>Window</span>
            <select class="form-control is-small" bind:value={windowId} aria-label="Window">
              {#each CRITERION_WINDOWS as option}
                <option value={option.id}>{option.label}</option>
              {/each}
            </select>
          </label>
        {/if}

        <label class="field">
          <span>Cadence</span>
          <select class="form-control is-small" bind:value={cadence} aria-label="Cadence">
            {#each definition.cadences as option}
              <option value={option}>{CADENCE_LABELS[option]}</option>
            {/each}
          </select>
          {#if cadence === "intraday" && (!definition.intraday_capable || !registry?.tws_connected)}
            <span class="field-note warn"
              >{definition.intraday_capable ? "Needs Trader Workstation; daily close until it connects." : "No intraday source; evaluated at the daily close."}</span
            >
          {/if}
        </label>

        <label class="field wide">
          <span>Label</span>
          <input
            class="form-control is-small"
            value={labelText}
            maxlength="200"
            on:input={(event) => {
              labelText = event.currentTarget.value;
              labelTouched = Boolean(labelText.trim());
            }}
            aria-label="Criterion label"
          />
        </label>

        <div class="preview-row wide">
          <button type="button" class="btn is-small is-ghost" disabled={!paramsComplete(definition, params) || previewing} on:click={checkNow}
            >{previewing ? "Reading…" : "Check now"}</button
          >
          {#if preview}
            <span class="preview-text" class:warn={!preview.available || preview.stale_reason}>
              Now: {previewText(preview)}{#if preview.stale_reason} · {preview.stale_reason}{/if}
            </span>
          {/if}
        </div>
      {/if}

      {#if formError}<p class="form-error wide" role="alert">{formError}</p>{/if}

      <div class="form-actions wide">
        <button type="button" class="btn is-small is-ghost" on:click={() => (formOpen = false)}>Cancel</button>
        <button type="submit" class="btn is-small is-primary" disabled={!complete || saving} title={saveHint}
          >{saving ? (evaluable ? "Saving and evaluating…" : "Saving…") : editingId ? "Save criterion" : "Add criterion"}</button
        >
      </div>
      <datalist id={`${formId}-tickers`}>{#each suggestions.tickers as item}<option value={item}></option>{/each}</datalist>
      <datalist id={`${formId}-contracts`}>{#each suggestions.contracts as item}<option value={item}></option>{/each}</datalist>
    </form>
  {/if}

  <div class="table-scroll">
    <table class="data-table is-top criteria-table">
      <colgroup>
        <col class="col-criterion" />
        <col class="col-now" />
        <col class="col-state" />
        <col class="col-cadence" />
        <col class="col-triggered" />
        <col class="col-actions" />
      </colgroup>
      <thead>
        <tr>
          <th>Criterion</th>
          <th class="num">Now</th>
          <th>State</th>
          <th>Cadence</th>
          <th>Triggered</th>
          <th><span class="sr-only">Actions</span></th>
        </tr>
      </thead>
      <tbody>
        {#each idea.criteria as criterion (criterion.criterion_id)}
          {@const now = criterionNowText(criterion)}
          {@const evaluation = criterion.last_evaluation}
          {@const trigger = criterion.trigger_evaluation}
          {@const def = definitionFor(criterion)}
          <tr class:is-triggered={criterion.state === "triggered"} data-state={criterion.state}>
            <td class="criterion-cell" title={criterionArmedText(criterion, formatIdeaInstant(criterion.armed_at))}>
              <strong>{criterion.label}</strong>
              <span class="meta"
                >{CRITERION_KIND_LABELS[criterion.kind]} · <span title={def?.source ?? ""}>{criterion.observable.label}</span><WhatIsThis
                  key={`observable.${criterion.observable.observable_id}`}
                  stance={idea.stance}
                  provenance={evaluation?.provenance ?? null}
                /></span
              >
            </td>
            <td class="num now-cell" class:absent={!evaluation || evaluation.value_display == null}>
              <span>{now.value}</span>
              {#if now.detail || evaluation?.provenance}
                <span class="meta now-meta"
                  >{now.detail}{#if evaluation?.provenance}<ProvenanceBadge
                      data={toProvenanceBadge({ ...evaluation.provenance, warnings: evaluation.warnings })}
                      variant="dot"
                      showTime={false}
                    />{/if}</span
                >
              {/if}
            </td>
            <td class="state-cell">
              <span class="state-line">
                <span class="tag {criterionStateTone(criterion.state, criterion.kind)}">{CRITERION_STATE_LABELS[criterion.state]}</span>
                <WhatIsThis
                  key={`state.${criterion.state}`}
                  stance={idea.stance}
                  provenance={evaluation?.provenance ?? null}
                  note={evaluation?.reason ?? ""}
                />
              </span>
              {#if criterion.state !== "triggered" && evaluation?.reason}
                <span class="meta reason">{evaluation.reason}</span>
              {:else if criterion.state === "triggered" && evaluation && evaluation.state !== "triggered"}
                <span class="meta reason">Latest reading: {CRITERION_STATE_LABELS[evaluation.state].toLowerCase()}{evaluation.reason ? `, ${evaluation.reason}` : ""}</span>
              {/if}
            </td>
            <td class="cadence-cell">
              <span>{CADENCE_LABELS[criterion.cadence]}</span>
              {#if evaluation?.cadence_note}<span class="meta reason">{evaluation.cadence_note}</span>{/if}
            </td>
            <td class="triggered-cell" class:absent={!criterion.triggered_at}>
              {#if criterion.triggered_at}
                <span>{trigger?.met_display ?? trigger?.value_display ?? "N/A"}</span>
                <span class="meta">{trigger?.first_met_at ? `First met ${shortDate(trigger.first_met_at)}` : ""}</span>
                <span class="meta">{detectedText(criterion)}</span>
              {:else}
                Not triggered
              {/if}
            </td>
            <td class="actions-cell">
              {#if criterion.triggered_at && !criterion.acknowledged_at}
                <button type="button" class="btn is-small is-ghost" on:click={() => onAcknowledge(criterion.criterion_id)}>Acknowledge</button>
              {/if}
              <button type="button" class="btn is-small is-ghost" disabled={idea.status !== "draft" && idea.status !== "active"} on:click={() => openForm(criterion)}>Edit</button>
              <button
                type="button"
                class="btn is-small"
                class:is-danger={confirmRemove === criterion.criterion_id}
                class:is-ghost={confirmRemove !== criterion.criterion_id}
                on:click={() => remove(criterion)}>{confirmRemove === criterion.criterion_id ? "Confirm remove" : "Remove"}</button
              >
            </td>
          </tr>
        {:else}
          <tr class="empty-row">
            <td colspan="6">No criteria yet. Add what would prove the thesis wrong before the outcome is known.</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="criteria-foot">
    {#if idea.status === "draft"}Draft ideas are not evaluated; activating the idea arms every criterion.{:else}Evaluated only while Gamma runs: at start, when the idea opens, after each US close, and intraday with Trader Workstation.{/if}
  </p>
</article>

<style>
  .criteria-title {
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .criteria-title h3 {
    display: inline-flex;
    align-items: center;
  }

  .title-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
    margin-left: auto;
  }

  .criterion-form {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
    gap: var(--space-4);
    padding: 0 var(--space-5) var(--space-5);
  }

  .field {
    display: grid;
    align-content: start;
    gap: var(--space-1);
    min-width: 0;
  }

  .field > span:first-child {
    display: inline-flex;
    align-items: center;
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .field :global(select),
  .field :global(input) {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
  }

  .wide {
    grid-column: 1 / -1;
  }

  .kind-row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .field-note {
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .field-note.warn,
  .preview-text.warn {
    color: var(--warning);
  }

  .preview-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .preview-text {
    color: var(--text-1);
    font-family: var(--font-num);
    font-size: var(--text-sm);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .form-error {
    margin: 0;
    color: var(--negative);
    font-size: var(--text-sm);
  }

  /* Positioned, so the visually hidden header labels stay inside the scroll
     box instead of widening the page on a narrow window. */
  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .criteria-table {
    table-layout: fixed;
    min-width: 50rem;
  }

  .col-criterion {
    width: 36%;
  }

  .col-now {
    width: 8.5rem;
  }

  .col-state {
    width: 19%;
  }

  .col-cadence {
    width: 7rem;
  }

  .col-triggered {
    width: 8.5rem;
  }

  .col-actions {
    width: 12.5rem;
  }

  .criterion-cell,
  .now-cell,
  .state-cell,
  .cadence-cell,
  .triggered-cell {
    overflow-wrap: anywhere;
  }

  .now-cell .now-meta {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-2);
  }

  td .meta {
    display: block;
  }

  .state-line {
    display: inline-flex;
    align-items: center;
  }

  .reason {
    margin-top: var(--space-1);
  }

  .actions-cell {
    text-align: right;
    white-space: nowrap;
  }

  .actions-cell .btn + .btn {
    margin-left: var(--space-2);
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .criteria-foot {
    margin: 0;
    padding: var(--space-3) var(--space-5) var(--space-4);
    color: var(--text-2);
    font-size: var(--text-2xs);
  }
</style>
