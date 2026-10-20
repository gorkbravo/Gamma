<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import type { SetupDataMode, SetupReport, SystemStatus } from "../lib/api/types";
  import {
    buildSetupChoices,
    coverageSourceLabel,
    coverageSourceTone,
    dataModeLabel,
    dataModeLocked,
    draftChanges,
    initialDraft,
    initialStepIndex,
    lockedNote,
    restartNeeded,
    SEC_EMAIL_MAX,
    SEC_NAME_MAX,
    secIdentityLocked,
    setupSteps,
    stepLabel,
    validateSecIdentity,
    type SetupChoices,
    type SetupDraft,
    type SetupStepId
  } from "../lib/setup-wizard";
  import type { SetupFinishResult } from "../lib/stores/setup";

  export let report: SetupReport | null = null;
  export let status: SystemStatus | null = null;
  export let firstRun = false;
  // Paso con el que abrir (p. ej. "identity" desde el aviso de Fundamentals).
  export let initialStep: SetupStepId | null = null;
  export let loading = false;
  export let loadError = "";
  export let connectionBusy = false;
  export let onClose: () => void;
  export let onSkip: () => Promise<boolean>;
  export let onFinish: (choices: SetupChoices) => Promise<SetupFinishResult>;
  export let onTestConnection: () => Promise<void>;
  export let onRetry: () => void;

  const STEP_TITLES: Record<SetupStepId, string> = {
    mode: "How do you want to start?",
    broker: "Connect Trader Workstation",
    preferences: "Preferences",
    sources: "What each tab will show",
    identity: "SEC EDGAR identity",
    review: "Review and finish"
  };

  let draft: SetupDraft | null = null;
  let stepIndex = 0;
  let saving = false;
  let errorText = "";
  let result: SetupFinishResult | null = null;
  let headingEl: HTMLHeadingElement | null = null;
  let dialogEl: HTMLDivElement | null = null;
  let previouslyFocused: HTMLElement | null = null;

  // El borrador se crea una sola vez con el primer informe; refrescos posteriores no lo pisan.
  $: if (report && draft == null) {
    draft = initialDraft(report, status);
    stepIndex = initialStepIndex(setupSteps(draft.dataMode), initialStep);
  }
  $: steps = draft ? setupSteps(draft.dataMode) : (["mode"] as SetupStepId[]);
  $: if (stepIndex > steps.length - 1) stepIndex = steps.length - 1;
  $: step = steps[stepIndex];
  $: identityError = draft ? validateSecIdentity(draft.secName, draft.secEmail) : null;
  $: changes = report && draft ? draftChanges(report, status, draft) : [];
  $: coverage = report && draft ? report.coverage_by_mode[draft.dataMode] ?? [] : [];
  $: modeLocked = report ? dataModeLocked(report) : false;
  $: needsRestart = report && draft ? restartNeeded(report, draft) : false;
  $: currentCurrency = status?.base_currency ?? report?.base_currency.current ?? "";
  $: title = result
    ? "Setup saved"
    : report && draft
      ? STEP_TITLES[step]
      : loadError
        ? "Setup unavailable"
        : "Reading setup status";
  $: isLast = stepIndex === steps.length - 1;
  $: canAdvance = !(step === "identity" && identityError);

  onMount(() => {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    void tick().then(() => headingEl?.focus());
  });

  onDestroy(() => {
    previouslyFocused?.focus?.();
  });

  async function focusHeading() {
    await tick();
    headingEl?.focus();
  }

  async function goTo(index: number) {
    stepIndex = Math.max(0, Math.min(index, steps.length - 1));
    errorText = "";
    await focusHeading();
  }

  function setDataMode(mode: SetupDataMode) {
    if (!draft || modeLocked) return;
    draft = { ...draft, dataMode: mode };
  }

  async function finish() {
    if (!report || !draft || saving) return;
    saving = true;
    errorText = "";
    const outcome = await onFinish(buildSetupChoices(report, status, draft));
    saving = false;
    if (!outcome.ok) {
      errorText = outcome.error ?? "Setup could not be saved.";
      return;
    }
    result = outcome;
    await focusHeading();
  }

  async function skip() {
    if (saving) return;
    saving = true;
    errorText = "";
    const ok = await onSkip();
    saving = false;
    if (ok) onClose();
    else errorText = "Setup could not be saved. You can close this window and run setup later from Settings.";
  }

  function focusableElements(): HTMLElement[] {
    if (!dialogEl) return [];
    return Array.from(
      dialogEl.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
      )
    );
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    // Mantiene el foco dentro del diálogo modal.
    const items = focusableElements();
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === headingEl)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function ibkrStatusLabel(current: SetupReport): string {
    if (current.data_mode.current === "demo") return "Checked after restart";
    return current.ibkr.status === "connected" ? "Connected" : "Not connected";
  }

  function copilotStatusLabel(current: SetupReport): string {
    switch (current.copilot.status) {
      case "configured":
        return "Configured";
      case "demo":
        return "Demo answers";
      case "missing_key":
        return "Not set";
      case "disabled":
        return "Disabled";
      default:
        return "Unavailable";
    }
  }
</script>

<div class="backdrop">
  <div
    class="dialog"
    role="dialog"
    aria-modal="true"
    aria-labelledby="setup-title"
    tabindex="-1"
    bind:this={dialogEl}
    on:keydown={handleKeydown}
  >
    <header class="head">
      <div class="titles">
        <span class="eyebrow">{firstRun ? "First-run setup" : "Setup"}</span>
        <h2 id="setup-title" tabindex="-1" bind:this={headingEl}>{title}</h2>
      </div>
      <button type="button" class="ghost close" aria-label="Close setup" on:click={onClose}>Close</button>
    </header>

    {#if report && draft && !result}
      <ol class="progress" aria-label="Setup steps">
        {#each steps as item, index}
          <li class:done={index < stepIndex} aria-current={index === stepIndex ? "step" : undefined}>
            <span class="index">{index + 1}</span>
            <span class="label">{stepLabel(item)}</span>
          </li>
        {/each}
      </ol>
    {/if}

    <div class="body">
      {#if result}
        <div class="result" role="status">
          {#if result.restartRequired && draft}
            <p class="notice warning">
              Restart Gamma to switch to {dataModeLabel(draft.dataMode).toLowerCase()}. Until then Gamma keeps running in
              {report ? dataModeLabel(report.data_mode.current).toLowerCase() : "its current mode"}.
            </p>
          {/if}
          {#if result.lines.length}
            <ul class="lines">
              {#each result.lines as line}
                <li>{line}</li>
              {/each}
            </ul>
          {:else}
            <p class="muted">Your preferences are saved. Run setup again any time from Settings.</p>
          {/if}
        </div>
      {:else if !report || !draft}
        {#if loadError}
          <p class="notice warning" role="alert">Gamma could not read its setup status: {loadError}</p>
        {:else}
          <p class="muted" aria-live="polite">{loading ? "LOADING..." : "Waiting for the backend."}</p>
        {/if}
      {:else if step === "mode"}
        <fieldset class="modes" disabled={modeLocked}>
          <legend class="sr-only">Data mode</legend>
          <label class="mode" class:selected={draft.dataMode === "demo"}>
            <input
              type="radio"
              name="setup-data-mode"
              value="demo"
              checked={draft.dataMode === "demo"}
              aria-labelledby="setup-mode-demo"
              aria-describedby="setup-mode-demo-detail"
              on:change={() => setDataMode("demo")}
            />
            <span class="mode-copy">
              <strong id="setup-mode-demo">Demo</strong>
              <small id="setup-mode-demo-detail">Sample portfolio. No broker or API keys needed.</small>
              <span class="points">
                <span>Sample account, synthetic prices and option surfaces.</span>
                <span>Macro, prediction markets, crypto and SEC filings stay live when online.</span>
              </span>
            </span>
          </label>
          <label class="mode" class:selected={draft.dataMode === "live"}>
            <input
              type="radio"
              name="setup-data-mode"
              value="live"
              checked={draft.dataMode === "live"}
              aria-labelledby="setup-mode-live"
              aria-describedby="setup-mode-live-detail"
              on:change={() => setDataMode("live")}
            />
            <span class="mode-copy">
              <strong id="setup-mode-live">Live data</strong>
              <small id="setup-mode-live-detail">Your IBKR account, read-only.</small>
              <span class="points">
                <span>Positions, risk and option chains through TWS.</span>
                <span>Optional API keys add research providers.</span>
              </span>
            </span>
          </label>
        </fieldset>
        {#if modeLocked}
          <p class="note">{lockedNote(report.data_mode.locked_by)} Remove it there to choose here.</p>
        {:else if needsRestart}
          <p class="note">Takes effect after you restart Gamma.</p>
        {/if}
        {#each report.warnings as warning}
          <p class="notice warning">{warning}</p>
        {/each}
        <p class="note">Gamma is read-only: it never places orders or moves funds.</p>
      {:else if step === "broker"}
        <dl class="facts">
          <div>
            <dt>Status</dt>
            <dd class:positive={report.ibkr.status === "connected"}>{ibkrStatusLabel(report)}</dd>
          </div>
          <div>
            <dt>Address</dt>
            <dd class="mono">{report.ibkr.host}:{report.ibkr.port}</dd>
          </div>
          <div>
            <dt>Client ID</dt>
            <dd class="mono">{report.ibkr.client_id}</dd>
          </div>
        </dl>
        <p class="muted">
          {report.data_mode.current === "demo"
            ? "Gamma is running in demo now. It connects to TWS after you restart on live data."
            : report.ibkr.detail}
        </p>
        {#if report.ibkr.steps.length}
          <ol class="steps">
            {#each report.ibkr.steps as item}
              <li>{item}</li>
            {/each}
          </ol>
        {/if}
        <p class="note">Change the address with IB_HOST, IB_PORT and IB_CLIENT_ID in the environment or .env file.</p>
        {#if report.data_mode.current === "live" && report.ibkr.status !== "connected"}
          <button type="button" class="ghost" disabled={connectionBusy} on:click={() => void onTestConnection()}>
            {connectionBusy ? "Connecting..." : "Test connection"}
          </button>
        {/if}
      {:else if step === "preferences"}
        <div class="fields">
          <label class="field">
            <span class="field-label">Base currency</span>
            <select bind:value={draft.baseCurrency} disabled={report.base_currency.locked_by != null}>
              {#each report.base_currency.options as option}
                <option value={option}>{option}</option>
              {/each}
            </select>
            {#if report.base_currency.locked_by}
              <small>{lockedNote(report.base_currency.locked_by)}</small>
            {:else if draft.baseCurrency !== currentCurrency}
              <small class="warning-text">Changing it archives local portfolio history, which is stored per currency.</small>
            {:else}
              <small>Portfolio values, risk and performance are reported in this currency.</small>
            {/if}
          </label>
          {#if draft.dataMode === "live"}
            <label class="field">
              <span class="field-label">Market data</span>
              <select bind:value={draft.marketDataMode} disabled={report.market_data_mode.locked_by != null}>
                <option value="delayed">Delayed</option>
                <option value="live">Live</option>
                <option value="auto">Auto</option>
              </select>
              <small>
                {report.market_data_mode.locked_by
                  ? lockedNote(report.market_data_mode.locked_by)
                  : "Delayed quotes are free. Live and Auto request real-time quotes, which need IBKR market-data subscriptions."}
              </small>
            </label>
          {/if}
        </div>
      {:else if step === "sources"}
        <table class="grid">
          <caption>{dataModeLabel(draft.dataMode)}: source by tab</caption>
          <thead>
            <tr>
              <th scope="col">Tab</th>
              <th scope="col">Source</th>
              <th scope="col">Detail</th>
            </tr>
          </thead>
          <tbody>
            {#each coverage as row}
              <tr>
                <th scope="row">{row.label}</th>
                <td class={coverageSourceTone(row.source)}>{coverageSourceLabel(row.source)}</td>
                <td>{row.detail}</td>
              </tr>
            {/each}
          </tbody>
        </table>

        <table class="grid">
          <caption>Optional keys</caption>
          <thead>
            <tr>
              <th scope="col">Provider</th>
              <th scope="col">Status</th>
              <th scope="col">Adds</th>
              <th scope="col">Variable</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Copilot</th>
              <td class:positive={report.copilot.status === "configured"}>{copilotStatusLabel(report)}</td>
              <td>Model-backed research answers in Copilot. Requests are billed to your OpenAI account.</td>
              <td class="mono">OPENAI_API_KEY</td>
            </tr>
            {#each report.providers as provider}
              <tr>
                <th scope="row">{provider.display_name}</th>
                <td class:positive={provider.configured}>{provider.configured ? "Configured" : "Not set"}</td>
                <td>{provider.unlocks}</td>
                <td class="mono">{provider.env_vars.join(", ")}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <p class="note">
          Gamma reads API keys from environment variables or the .env file
          {#if report.config.env_file_path}<span class="mono path">{report.config.env_file_path}</span>{/if}
          {report.config.env_file_present ? "" : "(not created yet)"} and never stores them. Restart Gamma after editing keys.
        </p>
      {:else if step === "identity"}
        <p class="muted">
          SEC EDGAR asks automated tools to say who is making requests. Gamma sends this name and email only to sec.gov,
          in each request's User-Agent header, and keeps them on this computer.
        </p>
        {#if secIdentityLocked(report)}
          <p class="note">{report.sec_identity.detail}</p>
        {:else}
          <div class="fields">
            <label class="field">
              <span class="field-label">Name</span>
              <input
                type="text"
                autocomplete="name"
                maxlength={SEC_NAME_MAX}
                bind:value={draft.secName}
                disabled={draft.clearSecIdentity}
                aria-invalid={identityError ? "true" : undefined}
                aria-describedby="setup-identity-help"
              />
            </label>
            <label class="field">
              <span class="field-label">Email</span>
              <input
                type="email"
                autocomplete="email"
                maxlength={SEC_EMAIL_MAX}
                bind:value={draft.secEmail}
                disabled={draft.clearSecIdentity}
                aria-invalid={identityError ? "true" : undefined}
                aria-describedby="setup-identity-help"
              />
            </label>
          </div>
          <p id="setup-identity-help" class:warning-text={identityError} class="note">
            {identityError ??
              (report.sec_identity.status === "missing" && !draft.secName && !draft.secEmail
                ? "Required for Fundamentals, Copilot company lookup, Script Fundamentals exports and SEC press releases. Leave both empty to decide later."
                : "Leave both fields unchanged to keep the current identity.")}
          </p>
          {#if report.sec_identity.source === "setup"}
            <label class="check">
              <input type="checkbox" bind:checked={draft.clearSecIdentity} />
              <span>Remove the saved identity</span>
            </label>
          {/if}
        {/if}
      {:else if step === "review"}
        {#if changes.length}
          <table class="grid">
            <caption class="sr-only">Changes applied when you finish</caption>
            <thead>
              <tr>
                <th scope="col">Setting</th>
                <th scope="col">Now</th>
                <th scope="col">After</th>
                <th scope="col">Note</th>
              </tr>
            </thead>
            <tbody>
              {#each changes as change}
                <tr>
                  <th scope="row">{change.label}</th>
                  <td>{change.from}</td>
                  <td>{change.to}</td>
                  <td>{change.note ?? ""}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="muted">No changes. Finishing marks setup as complete; run it again any time from Settings.</p>
        {/if}
      {/if}

      {#if errorText}
        <p class="notice warning" role="alert">{errorText}</p>
      {/if}
    </div>

    <footer class="foot">
      {#if result}
        <span></span>
        <button type="button" class="primary" on:click={onClose}>Done</button>
      {:else if !report || !draft}
        <span></span>
        {#if loadError}
          <button type="button" class="ghost" on:click={onRetry} disabled={loading}>Retry</button>
        {/if}
      {:else}
        <div class="left">
          {#if stepIndex > 0}
            <button type="button" class="ghost" on:click={() => void goTo(stepIndex - 1)} disabled={saving}>Back</button>
          {:else if firstRun}
            <button type="button" class="ghost" on:click={() => void skip()} disabled={saving}>Skip setup</button>
          {/if}
        </div>
        {#if isLast}
          <button type="button" class="primary" on:click={() => void finish()} disabled={saving}>
            {saving ? "Saving..." : "Finish setup"}
          </button>
        {:else}
          <button type="button" class="primary" on:click={() => void goTo(stepIndex + 1)} disabled={!canAdvance}>
            Next: {stepLabel(steps[stepIndex + 1])}
          </button>
        {/if}
      {/if}
    </footer>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    /* Por encima de shelf y menús (≤ 60), por debajo de los tooltips (200). */
    z-index: 100;
    display: grid;
    place-items: center;
    padding: var(--space-6);
    background: color-mix(in srgb, var(--bg-0) 78%, transparent);
  }

  /* Superficie de overlay: el único caso en que el modelo de planos admite sombra. */
  .dialog {
    width: min(54rem, 100%);
    max-height: calc(100vh - 2 * var(--space-6));
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr) auto;
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-md);
    background: var(--surface-0);
    box-shadow: 0 24px 56px var(--shadow);
    outline: none;
  }

  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-5);
    padding: var(--space-6) var(--space-6) var(--space-5);
    border-bottom: 1px solid var(--panel-border);
  }

  .titles {
    display: grid;
    gap: var(--space-2);
  }

  .eyebrow,
  dt,
  .field-label,
  th[scope="col"],
  caption {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: var(--text-2xs);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  h2 {
    margin: 0;
    color: var(--text-0);
    font-family: var(--display-font);
    font-size: var(--text-lg);
    line-height: var(--leading-tight);
    outline: none;
  }

  .progress {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-6);
    margin: 0;
    padding: var(--space-4) var(--space-6);
    list-style: none;
    border-bottom: 1px solid var(--panel-border);
    font-family: var(--display-font);
    font-size: var(--text-xs);
  }

  .progress li {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-2);
  }

  .progress .index {
    font-family: var(--app-font);
  }

  .progress li.done {
    color: var(--text-1);
  }

  .progress li[aria-current="step"] {
    color: var(--text-0);
  }

  .progress li[aria-current="step"] .index {
    color: var(--accent);
  }

  .body {
    display: grid;
    align-content: start;
    gap: var(--space-5);
    min-height: 16rem;
    padding: var(--space-6);
    overflow: auto;
    color: var(--text-1);
    font-family: var(--display-font);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
  }

  p {
    margin: 0;
  }

  .muted {
    color: var(--text-1);
  }

  .note {
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .notice {
    padding: var(--space-4) var(--space-5);
    border: 1px solid var(--panel-border);
    border-left: 2px solid var(--warning);
    font-size: var(--text-sm);
  }

  .warning-text,
  .warning {
    color: var(--warning);
  }

  .positive {
    color: var(--positive);
  }

  .neutral {
    color: var(--text-1);
  }

  .mono {
    font-family: var(--app-font);
  }

  .path {
    word-break: break-all;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  /* Paso 1: dos opciones nativas de radio con el texto como etiqueta. */
  .modes {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    border: 0;
  }

  .mode {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
    padding: var(--space-5);
    border: 1px solid var(--panel-border);
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: border-color var(--motion-fast) var(--ease), background var(--motion-fast) var(--ease);
  }

  .mode:hover {
    background: var(--hover-bg);
  }

  .mode.selected {
    border-color: color-mix(in srgb, var(--accent) 60%, var(--panel-strong));
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  .modes:disabled .mode {
    cursor: not-allowed;
    opacity: 0.7;
  }

  .mode input {
    margin: var(--space-1) 0 0;
    accent-color: var(--accent);
  }

  .mode-copy {
    display: grid;
    gap: var(--space-2);
  }

  .mode-copy strong {
    color: var(--text-0);
    font-size: var(--text-md);
  }

  .mode-copy small {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .points {
    display: grid;
    gap: var(--space-2);
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .facts {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0;
    margin: 0;
    border: 1px solid var(--panel-border);
  }

  .facts div {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-4) var(--space-5);
  }

  .facts div + div {
    border-left: 1px solid var(--panel-border);
  }

  dd {
    margin: 0;
    color: var(--text-0);
    font-family: var(--app-font);
  }

  .steps {
    display: grid;
    gap: var(--space-3);
    margin: 0;
    padding-left: var(--space-7);
  }

  .fields {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-5);
  }

  .field {
    display: grid;
    gap: var(--space-2);
    align-content: start;
  }

  .field small {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .field small.warning-text {
    color: var(--warning);
  }

  select,
  input[type="text"],
  input[type="email"] {
    min-height: 30px;
    padding: 0 var(--space-4);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    background: var(--bg-1);
    color: var(--text-0);
    font-family: var(--app-font);
    font-size: var(--text-sm);
  }

  input[aria-invalid="true"] {
    border-color: var(--warning);
  }

  select:disabled,
  input:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }

  .check {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    font-size: var(--text-sm);
  }

  .grid {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
  }

  .grid caption {
    padding-bottom: var(--space-3);
    text-align: left;
  }

  .grid th,
  .grid td {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    text-align: left;
    vertical-align: top;
  }

  .grid th[scope="row"] {
    color: var(--text-0);
    font-weight: 500;
    white-space: nowrap;
  }

  .grid td:nth-child(2) {
    white-space: nowrap;
  }

  .lines {
    display: grid;
    gap: var(--space-3);
    margin: 0;
    padding-left: var(--space-6);
  }

  .result {
    display: grid;
    gap: var(--space-5);
  }

  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-5) var(--space-6);
    border-top: 1px solid var(--panel-border);
  }

  button {
    min-height: 28px;
    padding: 0 var(--space-5);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    background: var(--bg-1);
    color: var(--text-0);
    font-family: var(--display-font);
    font-size: var(--text-sm);
    font-weight: 500;
    cursor: pointer;
    transition: border-color var(--motion-fast) var(--ease), background var(--motion-fast) var(--ease);
  }

  button:hover:enabled {
    border-color: color-mix(in srgb, var(--accent) 55%, var(--panel-strong));
    background: var(--hover-bg);
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .primary {
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }

  .ghost {
    background: transparent;
  }

  .close {
    flex-shrink: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    .mode,
    button {
      transition: none;
    }
  }

  @media (max-width: 640px) {
    .backdrop {
      padding: var(--space-4);
    }

    .dialog {
      max-height: calc(100vh - 2 * var(--space-4));
    }

    .modes,
    .fields,
    .facts {
      grid-template-columns: 1fr;
    }

    .facts div + div {
      border-left: 0;
      border-top: 1px solid var(--panel-border);
    }

    /* En móvil la tabla mantiene su semántica pero parte el texto en lugar de desbordar. */
    .grid th,
    .grid td {
      padding: var(--space-3) var(--space-2);
    }

    .grid th[scope="row"],
    .grid td:nth-child(2) {
      white-space: normal;
    }

    /* Los nombres de variable (COMMODITIES_PROVIDER=eia...) son tokens largos sin espacios;
       solo se parten en las columnas de detalle, nunca en el nombre de pestaña ni en la fuente. */
    .grid td:not(:nth-child(2)) {
      overflow-wrap: anywhere;
    }
  }
</style>
