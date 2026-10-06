<script lang="ts">
  import CommoditiesView from "../views/CommoditiesView.svelte";
  import { postJson } from "../lib/api/client";
  import type { CommodityWorkspaceResponse } from "../lib/api/types";
  import type { CommodityWorkspaceLoadOptions } from "../lib/stores/app";
  let workspace: CommodityWorkspaceResponse | null = null, loading = false, error = "";
  async function load(options?: CommodityWorkspaceLoadOptions) {
    loading = true; error = "";
    try { workspace = await postJson<CommodityWorkspaceResponse>("/commodities/workspace", {
      mode: options?.mode ?? "curves_spreads", selected_instrument_id: options?.selectedInstrumentId ?? "wti", force_refresh: options?.forceRefresh ?? false
    }); } catch (e) { error = String(e); } finally { loading = false; }
  }
</script>
{#if error}<p role="alert">{error}</p>{/if}
<CommoditiesView {workspace} {loading} mode="curves_spreads" onLoadWorkspace={load} />
<style>:global(body) { margin: 0; background: var(--bg-0); color: var(--text-0); } :global(#app) { padding: 12px; }</style>
