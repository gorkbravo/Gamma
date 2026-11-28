<script context="module" lang="ts">
  export type GuideSection = "guide" | "privacy";
</script>

<script lang="ts">
  // Guía de primeros pasos y nota de privacidad para testers de la beta (2026-11-28).
  // Todo lo que afirma está contrastado con el código: si cambia un flujo o un dato que sale
  // del equipo, actualiza también este texto y el README («Beta testers» y «Privacy»).
  import ModalFrame from "./ModalFrame.svelte";

  export let initialSection: GuideSection = "guide";
  // Ruta del .env que muestra Setup (null mientras no se ha leído el informe).
  export let envFilePath: string | null = null;
  export let onClose: () => void;
  export let onOpenSetup: () => void = () => {};
  export let onReportProblem: () => void = () => {};

  let section: GuideSection = initialSection;
</script>

<ModalFrame
  titleId="getting-started-title"
  title={section === "guide" ? "Getting started" : "Privacy"}
  eyebrow="Gamma beta"
  closeLabel="Close getting started"
  {onClose}
>
  <div class="switch" role="group" aria-label="Section" slot="nav">
    <button type="button" class="seg" aria-pressed={section === "guide"} on:click={() => (section = "guide")}>Getting started</button>
    <button type="button" class="seg" aria-pressed={section === "privacy"} on:click={() => (section = "privacy")}>Privacy</button>
  </div>

  {#if section === "guide"}
    <p class="lead">
      Gamma is a research environment. It reads market, macro and portfolio data and helps you analyse it; it never places
      orders or changes your brokerage account.
    </p>

    <section>
      <h4>1. Choose how to start</h4>
      <p>
        Demo mode uses a sample account and needs no broker or keys. Live mode reads your Interactive Brokers account through
        Trader Workstation (read-only) and the data providers you add keys for. Change the mode, keys and SEC identity in
        <button type="button" class="link" on:click={onOpenSetup}>Setup</button>.
      </p>
    </section>

    <section>
      <h4>2. Morning check: Sitrep to Ideas</h4>
      <p>
        Start in <strong>Sitrep</strong> for the market overview. When a figure matters, use <strong>Pin to idea</strong>
        on its panel to keep it, as shown, in a new or existing idea. <strong>Ideas</strong> then tracks each idea's
        criteria and signals over time.
      </p>
    </section>

    <section>
      <h4>3. One company: Fundamentals to Risk</h4>
      <p>
        In the Research workspace, search a ticker in <strong>Fundamentals</strong> and review its statements and DCF
        valuation. The ticker stays selected in the top bar, so <strong>Risk</strong> computes its metrics for the same
        company when you open it.
      </p>
    </section>

    <section>
      <h4>4. A portfolio idea: Strategy Lab to Risk to Ideas</h4>
      <p>
        In <strong>Strategy Lab</strong>, enter tickers and weights and press <strong>Compose Portfolio</strong>. Use
        <strong>Open In Risk</strong> to stress the composed book, then <strong>Attach to idea</strong> to keep the
        result with the idea it supports.
      </p>
    </section>

    <section>
      <h4>5. Copilot</h4>
      <p>
        Choose what Copilot may look at in the <strong>Context</strong> menu. <strong>Agent</strong> answers within those
        contexts and can run their read-only analyses. <strong>Operator</strong> can also plan multi-step research across
        Gamma's tools and pauses for your approval before changing anything saved. Copilot needs an OpenAI key; without
        one it gives demo answers or is unavailable.
      </p>
    </section>

    <section>
      <h4>Something wrong?</h4>
      <p>
        Use <button type="button" class="link" on:click={onReportProblem}>Report a problem</button>. You see the whole
        report first and send it yourself.
      </p>
    </section>
  {:else}
    <p class="lead">
      Gamma has no accounts, analytics or crash reporting. It sends nothing to the Gamma team; data leaves this computer
      only in the requests listed below.
    </p>

    <section>
      <h4>Kept on this computer</h4>
      <ul>
        <li>Your preferences and SEC identity, in Gamma's data folder.</li>
        <li>
          API keys, as plain text in the .env file
          {#if envFilePath}<span class="mono path">{envFilePath}</span>{/if}. Anyone who can sign in to this Windows
          account can read it.
        </li>
        <li>Ideas, saved research, Copilot conversations, portfolio history and data caches, in Gamma's data folder.</li>
        <li>Problem reports, only when you save one, in Gamma's data folder.</li>
      </ul>
      <p class="note">
        In the installed app, Gamma's data folder is <span class="mono path">%APPDATA%\com.gamma.shell\runtime</span>.
        Uninstalling keeps it unless you choose to delete the application data.
      </p>
    </section>

    <section>
      <h4>Sent from this computer</h4>
      <ul>
        <li>
          Requests to the data providers behind each tab (for example Yahoo Finance, FRED, SEC EDGAR or Polymarket). They
          include the tickers or series you look up and, where a provider needs one, your key for that provider. Demo mode
          uses sample data for most tabs but still makes some public requests.
        </li>
        <li>Your SEC identity (name and email), in the User-Agent header of requests to sec.gov and bls.gov only.</li>
        <li>
          In live mode, Gamma talks to Trader Workstation on this computer in read-only mode; Trader Workstation talks to
          Interactive Brokers.
        </li>
        <li>
          With an OpenAI key, your Copilot messages and the context you select, which can include portfolio figures, go to
          OpenAI and are billed to your account. OpenAI keeps Copilot responses for 30 days by default; set
          <span class="mono">GAMMA_COPILOT_STORE_RESPONSES=false</span> to turn that off. Strategy Lab scripts that run on
          OpenAI also send the script and its input data there.
        </li>
      </ul>
    </section>

    <section>
      <h4>Problem reports</h4>
      <p>
        <button type="button" class="link" on:click={onReportProblem}>Report a problem</button> builds the report on this
        computer. It never includes keys, account identifiers, positions, portfolio values, your SEC identity or research
        content, and you send it yourself.
      </p>
    </section>
  {/if}

  <svelte:fragment slot="footer">
    <span class="foot-note">Open this again from Settings or the start page.</span>
    <button type="button" class="btn is-primary" on:click={onClose}>Done</button>
  </svelte:fragment>
</ModalFrame>

<style>
  p {
    margin: 0;
  }

  .switch {
    display: flex;
    gap: var(--space-2);
    padding: var(--space-4) var(--space-6);
    border-bottom: 1px solid var(--panel-border);
  }

  .seg {
    padding: var(--space-2) var(--space-4);
    border: 1px solid transparent;
    border-radius: var(--panel-radius);
    background: transparent;
    color: var(--text-1);
    cursor: pointer;
    font-family: var(--font-ui);
    font-size: var(--text-sm);
    font-weight: 500;
    transition: background var(--motion-fast) var(--ease), border-color var(--motion-fast) var(--ease);
  }

  .seg:hover {
    background: var(--hover-bg);
  }

  .seg[aria-pressed="true"] {
    border-color: color-mix(in srgb, var(--accent) 60%, var(--panel-strong));
    background: var(--active-bg);
    color: var(--text-0);
  }

  .lead {
    color: var(--text-0);
  }

  section {
    display: grid;
    gap: var(--space-2);
  }

  h4 {
    margin: 0;
    color: var(--text-0);
    font-family: var(--font-ui);
    font-size: var(--text-base);
    font-weight: 500;
  }

  strong {
    color: var(--text-0);
    font-weight: 500;
  }

  ul {
    display: grid;
    gap: var(--space-2);
    margin: 0;
    padding-left: var(--space-6);
  }

  .mono {
    font-family: var(--font-num);
    font-size: var(--text-sm);
  }

  .path {
    overflow-wrap: anywhere;
  }

  .link {
    padding: 0;
    border: 0;
    background: none;
    color: var(--accent);
    cursor: pointer;
    font: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .foot-note,
  .note {
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  @media (prefers-reduced-motion: reduce) {
    .seg {
      transition: none;
    }
  }

  @media (max-width: 640px) {
    .switch {
      padding: var(--space-3) var(--space-5);
    }
  }
</style>
