<script lang="ts">
  // Arnés de la beta (2026-11-28): «Report a problem» y las claves del asistente con la API
  // sustituida por stubs que registran cada llamada en data-testid="calls".
  import ReportProblemDialog from "../components/ReportProblemDialog.svelte";
  import SetupWizard from "../components/SetupWizard.svelte";
  import type { DiagnosticReport, DiagnosticReportResponse } from "../lib/api/types";
  import { setupReportFixture } from "../lib/setup-wizard.fixture";
  import type { DiagnosticReportRequest } from "../lib/stores/setup";

  const view = new URLSearchParams(window.location.search).get("view") ?? "report";
  let calls: string[] = [];
  let clipboard = "";
  let closed = false;

  function record(entry: string) {
    calls = [...calls, entry];
  }

  function fakeReport(request: DiagnosticReportRequest): DiagnosticReport {
    return {
      schema: "gamma.diagnostic-report.v1",
      generated_at: "2026-11-28T10:00:00+00:00",
      app: { version: "0.1.0" },
      client: request.client ?? {},
      note: request.note ?? null,
      excluded: ["API keys and access tokens", "the SEC identity (name and email)"]
    };
  }

  async function preview(request: DiagnosticReportRequest): Promise<DiagnosticReportResponse> {
    record(`preview:${request.note ?? ""}`);
    return { report: fakeReport(request), path: null };
  }

  async function save(request: DiagnosticReportRequest): Promise<DiagnosticReportResponse> {
    record(`save:${request.note ?? ""}`);
    return { report: fakeReport(request), path: "C:/Gamma/logs/reports/gamma-report-20261128T100000Z.json" };
  }

  async function copyText(text: string) {
    if (view === "report-copy-fail") throw new Error("denied");
    clipboard = text;
    record("copy");
  }

  const report = setupReportFixture();
  async function onSaveKeys(keys: Record<string, string | null>) {
    record(`keys:${Object.keys(keys).join(",")}`);
    return { ok: true, lines: ["Saved FRED_API_KEY to C:/Gamma/.env.", "Restart Gamma to apply the change."], error: null };
  }
</script>

{#if view === "wizard"}
  <SetupWizard
    {report}
    initialStep="sources"
    onClose={() => (closed = true)}
    onSkip={async () => true}
    onFinish={async () => ({ ok: true, lines: [], error: null, currencyChanged: false, restartRequired: false })}
    onTestConnection={async () => {}}
    onRetry={() => {}}
    {onSaveKeys}
  />
{:else if !closed}
  <ReportProblemDialog
    client={{ active_tab: "risk", last_error: "" }}
    {preview}
    {save}
    {copyText}
    onClose={() => (closed = true)}
  />
{/if}

<pre data-testid="calls">{calls.join("\n")}</pre>
<pre data-testid="clipboard">{clipboard}</pre>
<span data-testid="closed">{closed ? "closed" : "open"}</span>
