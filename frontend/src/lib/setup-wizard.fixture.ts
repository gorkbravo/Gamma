import type { SetupReport } from "./api/types";

/* Informe de preparación de ejemplo para los tests del asistente (no lo importa la app). */
export function setupReportFixture(overrides: Partial<SetupReport> = {}): SetupReport {
  return {
    generated_at: "2026-10-19T12:00:00",
    schema_version: 1,
    first_run: true,
    completed_at: null,
    data_mode: {
      current: "demo",
      preference: null,
      source: "default",
      restart_required: false,
      locked_by: null,
      detail: "Sample portfolio and synthetic prices; free public research sources stay live when reachable."
    },
    base_currency: { current: "EUR", source: "default", locked_by: null, options: ["USD", "EUR", "GBP"] },
    market_data_mode: { current: "delayed", source: "default", locked_by: null, options: ["delayed", "live", "auto"] },
    ibkr: {
      status: "demo",
      host: "127.0.0.1",
      port: 7497,
      client_id: 1,
      account_configured: false,
      detail: "Demo mode does not connect to a broker.",
      steps: ["Start Trader Workstation (TWS) and log in."]
    },
    sec_identity: {
      status: "missing",
      source: "missing",
      locked_by: null,
      name: null,
      email: null,
      detail: "No SEC identity is configured."
    },
    copilot: {
      status: "missing_key",
      provider: "openai",
      detail: "Copilot needs OPENAI_API_KEY.",
      env_vars: ["GAMMA_COPILOT_PROVIDER", "OPENAI_API_KEY"]
    },
    providers: [
      {
        provider_id: "fred",
        display_name: "FRED",
        configured: false,
        env_vars: ["FRED_API_KEY"],
        unlocks: "FRED series in Macro."
      }
    ],
    coverage_by_mode: {
      demo: [
        { tab_id: "portfolio", label: "Portfolio", source: "sample", detail: "Sample IBKR-style account." },
        { tab_id: "macro", label: "Macro", source: "public", detail: "FRED, US Treasury." }
      ],
      live: [
        { tab_id: "portfolio", label: "Portfolio", source: "broker", detail: "Your IBKR account (not connected)." },
        { tab_id: "commodities", label: "Commodities", source: "unavailable", detail: "No live provider." }
      ]
    },
    config: { env_file_path: "C:/Gamma/.env", env_file_present: false, setup_file_path: "C:/Gamma/data/setup/setup.json" },
    warnings: [],
    ...overrides
  };
}
