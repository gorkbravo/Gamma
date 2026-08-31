<script lang="ts">
  import MacroDivergenceCard from "./MacroDivergenceCard.svelte";
  import MacroLinkedMarketRow from "./MacroLinkedMarketRow.svelte";
  import type {
    MacroContextState,
    MacroEvent,
    MacroEventReactionSignal,
    MacroEventStudy,
    MacroEventsResponse,
    MacroSnapshot,
    MacroTheme,
  } from "../lib/api/types";

  export let snapshot: MacroSnapshot | null = null;
  export let events: MacroEventsResponse | null = null;

  const themeLabels: Record<string, string> = {
    all: "All", growth: "Growth", inflation: "Inflation",
    policy: "Policy", recession_risk: "Recession Risk",
  };

  function shortDate(value: string | null | undefined) {
    return value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "N/A";
  }

  function eventStudyTone(label: string | null | undefined): string {
    if (label === "reinforcing") return "positive";
    if (label === "opposing") return "negative";
    return "";
  }

  function coherenceTone(label: string | null | undefined): string {
    if (label === "coherent") return "positive";
    if (label === "fractured") return "negative";
    if (label === "narrow") return "warning";
    return "";
  }

  function reactionTimingText(reaction: MacroEventReactionSignal | null | undefined): string | null {
    if (!reaction) return null;
    return [reaction.observed_label, reaction.lag_label].filter(Boolean).join(" | ") || null;
  }

  function groupEventsByMonth<T extends { scheduled_at: string }>(evts: T[]): Array<{ label: string; events: T[] }> {
    const groups: Array<{ label: string; events: T[] }> = [];
    let current = "";
    for (const event of evts) {
      if (!event.scheduled_at) continue;
      const d = new Date(event.scheduled_at);
      const key = d.toLocaleString("en-US", { month: "long", year: "numeric" });
      if (key !== current) { current = key; groups.push({ label: key, events: [] }); }
      groups.at(-1)!.events.push(event);
    }
    return groups;
  }

  $: eventRows = events?.events ?? snapshot?.upcoming_events ?? [];
  $: groupedEvents = groupEventsByMonth(eventRows);
  $: recentEventStudies = (snapshot?.event_studies ?? []).filter((study) => study.timing === "recent");
  $: upcomingEventStudies = (snapshot?.event_studies ?? []).filter((study) => study.timing === "upcoming");
</script>

<div class="events-layout">
  <!-- Regime Framing -->
  <article class="panel span-2">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Regime Framing</p>
        <h3>Current cross-market read</h3>
      </div>
    </div>
    {#if (snapshot?.top_divergences ?? []).length}
      <div class="card-grid">
        {#each snapshot?.top_divergences ?? [] as row}
          <MacroDivergenceCard
            headline={row.headline}
            summary={row.summary}
            score={row.score}
            label={row.label}
            theme={row.theme}
            coherence={row.coherence}
            primaryDriver={row.primary_driver}
            counterSignal={row.counter_signal}
            researchFocus={row.research_focus}
          />
        {/each}
      </div>
    {:else}
      <p class="empty-hint">No regime framing is available for this lens yet.</p>
    {/if}
  </article>

  <!-- Event Windows: Recent + Upcoming side by side -->
  {#if recentEventStudies.length || upcomingEventStudies.length}
    {#if recentEventStudies.length}
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Recent Windows</p>
            <h3>Post-event absorption</h3>
          </div>
        </div>
        <div class="study-list">
          {#each recentEventStudies as study}
            <article class="study-row">
              <div class="study-head">
                <strong>{study.event.title}</strong>
                <span class="tag {coherenceTone(study.coherence?.coherence_label)}">{themeLabels[study.theme] ?? study.theme}</span>
              </div>
              <span class="study-meta">
                <span class="event-date">{shortDate(study.event.scheduled_at)}</span>
                <span class="event-sep">·</span>
                <span>{study.window_label}</span>
              </span>
              <p class="study-summary">{study.summary}</p>

              {#if study.coherence}
                <div class="coherence-inline">
                  <span class="tag sm {coherenceTone(study.coherence.coherence_label)}">{study.coherence.coherence_label}</span>
                  <span class="coherence-stat">{study.coherence.supporting_signals} confirm · {study.coherence.opposing_signals} oppose</span>
                </div>
              {/if}

              {#if study.primary_reaction || study.counter_reaction}
                <div class="reaction-grid">
                  {#if study.primary_reaction}
                    <div class="reaction-brief">
                      <span class="reaction-role">Lead reaction</span>
                      <strong>{study.primary_reaction.metric.label}</strong>
                      <span class="reaction-score {eventStudyTone(study.primary_reaction.tone)}">{study.primary_reaction.signal_score_display}</span>
                    </div>
                  {/if}
                  {#if study.counter_reaction}
                    <div class="reaction-brief">
                      <span class="reaction-role">Lagging</span>
                      <strong>{study.counter_reaction.metric.label}</strong>
                      <span class="reaction-score {eventStudyTone(study.counter_reaction.tone)}">{study.counter_reaction.signal_score_display}</span>
                    </div>
                  {/if}
                </div>
              {/if}
            </article>
          {/each}
        </div>
      </article>
    {/if}

    {#if upcomingEventStudies.length}
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Upcoming Windows</p>
            <h3>Pre-event setup</h3>
          </div>
        </div>
        <div class="study-list">
          {#each upcomingEventStudies as study}
            <article class="study-row">
              <div class="study-head">
                <strong>{study.event.title}</strong>
                <span class="tag">{themeLabels[study.theme] ?? study.theme}</span>
              </div>
              <span class="study-meta">
                <span class="event-date">{shortDate(study.event.scheduled_at)}</span>
                <span class="event-sep">·</span>
                <span>{study.window_label}</span>
              </span>
              <p class="study-summary">{study.summary}</p>

              {#if study.coherence}
                <div class="coherence-inline">
                  <span class="tag sm {coherenceTone(study.coherence.coherence_label)}">{study.coherence.coherence_label}</span>
                  <span class="coherence-stat">{study.coherence.supporting_signals} confirm · {study.coherence.opposing_signals} oppose</span>
                </div>
              {/if}

              {#if study.primary_reaction || study.counter_reaction}
                <div class="reaction-grid">
                  {#if study.primary_reaction}
                    <div class="reaction-brief">
                      <span class="reaction-role">Lead setup</span>
                      <strong>{study.primary_reaction.metric.label}</strong>
                      <span class="reaction-score {eventStudyTone(study.primary_reaction.tone)}">{study.primary_reaction.signal_score_display}</span>
                    </div>
                  {/if}
                  {#if study.counter_reaction}
                    <div class="reaction-brief">
                      <span class="reaction-role">Counter</span>
                      <strong>{study.counter_reaction.metric.label}</strong>
                      <span class="reaction-score {eventStudyTone(study.counter_reaction.tone)}">{study.counter_reaction.signal_score_display}</span>
                    </div>
                  {/if}
                </div>
              {/if}

              {#if study.linked_markets?.length}
                <div class="linked-section">
                  {#each study.linked_markets as market}
                    <MacroLinkedMarketRow {market} />
                  {/each}
                </div>
              {/if}
            </article>
          {/each}
        </div>
      </article>
    {/if}
  {/if}

  <!-- Calendar -->
  <article class="panel span-2">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Calendar</p>
        <h3>Scheduled catalysts</h3>
      </div>
    </div>
    {#if groupedEvents.length}
      <div class="events-scroll">
        {#each groupedEvents as group}
          <div class="date-group-header">{group.label}</div>
          {#each group.events as event}
            <div class="list-row">
              <strong>{event.title}</strong>
              <span class="list-detail">
                <span class="event-date">{shortDate(event.scheduled_at)}</span>
                <span class="event-sep">·</span>
                <span class="event-category">{event.category}</span>
                <span class="event-sep">·</span>
                <span class="event-category">{event.importance}</span>
              </span>
            </div>
          {/each}
        {/each}
      </div>
    {:else}
      <p class="empty-hint">No event calendar entries are available for this region.</p>
    {/if}
  </article>
</div>

<style>
  .events-layout {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  /* ── Panel ── */

  .panel-header > div { min-width: 0; }
  .span-2 { grid-column: span 2; }

  /* ── Card grid ── */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  /* ── Study rows ── */
  .study-list {
    display: grid;
    gap: 0;
  }

  .study-row {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-4) 0;
    border-bottom: 1px solid rgba(46, 60, 74, 0.25);
  }

  .study-row:first-child { padding-top: 0; }
  .study-row:last-child { border-bottom: 0; }

  .study-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }

  .study-meta {
    display: flex;
    gap: var(--space-2);
    color: var(--text-2);
    font-size: var(--text-sm);
    align-items: center;
  }

  .study-summary {
    color: var(--text-2);
    margin: 0;
    font-size: var(--text-sm);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ── Coherence inline ── */
  .coherence-inline {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }

  .coherence-stat {
    color: var(--text-2);
    font-size: var(--text-2xs);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  /* ── Reaction grid ── */
  .reaction-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .reaction-brief {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
    padding: var(--space-2) 0;
  }

  .reaction-role {
    font-size: var(--text-2xs);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-2);
  }

  .reaction-brief strong {
    font-size: var(--text-sm);
    line-height: 1.3;
  }

  .reaction-score {
    font-size: var(--text-2xs);
    font-weight: 600;
    color: var(--text-1);
    margin-left: auto;
  }

  .reaction-score.positive { color: var(--positive); }
  .reaction-score.negative { color: var(--negative); }

  /* ── Linked markets ── */
  .linked-section {
    display: grid;
    gap: 0;
    border-top: 1px solid rgba(46, 60, 74, 0.18);
    padding-top: var(--space-1);
  }

  /* ── Tags ── */
  .tag {
    display: inline-block;
    border: 1px solid rgba(122, 166, 200, 0.24);
    background: rgba(122, 166, 200, 0.06);
    color: var(--accent);
    padding: var(--space-1) var(--space-3);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .tag.sm { font-size: var(--text-2xs); padding: var(--space-1) var(--space-2); }

  .tag.positive {
    border-color: rgba(75, 180, 116, 0.25);
    background: rgba(75, 180, 116, 0.06);
    color: var(--positive);
  }

  .tag.negative {
    border-color: rgba(198, 107, 97, 0.32);
    background: rgba(198, 107, 97, 0.08);
    color: var(--negative);
  }

  .tag.warning {
    border-color: rgba(196, 154, 90, 0.32);
    background: rgba(196, 154, 90, 0.08);
    color: var(--accent-2);
  }

  /* ── Lists & Events ── */
  .events-scroll {
    max-height: 24rem;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(122, 166, 200, 0.18) transparent;
  }

  .list-row {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-4) var(--space-5);
    border-bottom: 1px solid rgba(46, 60, 74, 0.3);
  }

  .list-row:first-child { padding-top: 0; }
  .list-row:last-child { border-bottom: 0; }

  .list-detail {
    display: flex;
    gap: var(--space-2);
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.35;
    align-items: center;
  }

  .event-date { color: var(--text-1); }
  .event-category { color: var(--text-2); }
  .event-sep { opacity: 0.4; }

  .date-group-header {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: var(--space-4) var(--space-5) var(--space-2);
    background: var(--surface-soft);
    border-bottom: 1px solid rgba(46, 60, 74, 0.2);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .empty-hint {
    color: var(--text-2);
    font-size: var(--text-sm);
    margin: 0;
    padding: var(--space-3) 0;
  }

  /* ── Typography ── */

  h3, p { margin: 0; }

  @media (max-width: 1080px) {
    .events-layout { grid-template-columns: 1fr; }
    .card-grid { grid-template-columns: 1fr; }
    .reaction-grid { grid-template-columns: 1fr; }
    .span-2 { grid-column: auto; }
  }
</style>
