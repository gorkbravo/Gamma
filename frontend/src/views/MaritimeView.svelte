<script module lang="ts">
  // Un handoff se aplica en una sola visita: volver a la pestaña no vuelve a encuadrar ni a avisar.
  const consumedFocusRequestIds = new Set<number>();
</script>

<script lang="ts">
  import { onMount } from "svelte";
  import MaritimeMap from "../components/MaritimeMap.svelte";
  import type { MaritimeMode, MaritimeWorkspaceResponse } from "../lib/api/types";
  import type { MaritimeLoadOptions } from "../lib/stores/app";
  import { resolveMaritimeFocus, type MaritimeFocusRequest } from "../lib/view-models/maritime";

  export let workspace: MaritimeWorkspaceResponse | null = null;
  export let loading = false;
  export let mode: MaritimeMode = "live_map";
  export let onLoadWorkspace: (options?: MaritimeLoadOptions) => Promise<unknown> | void;
  /** Petición de enfoque de un handoff entrante (GUA-20261021-7). */
  export let focusRequest: MaritimeFocusRequest | null = null;

  let map3D = false;
  let modeAppliedForRequestId: number | null = null;
  // Petición ya consumida en una visita anterior a la pestaña (se fija al montar).
  const staleFocusRequestId =
    focusRequest && consumedFocusRequestIds.has(focusRequest.requestId) ? focusRequest.requestId : null;

  // Se resuelve contra la geografía estática del workspace; null mientras no haya workspace.
  $: focus =
    focusRequest && focusRequest.requestId !== staleFocusRequestId ? resolveMaritimeFocus(focusRequest, workspace) : null;
  $: if (focus && focus.requestId !== modeAppliedForRequestId) {
    modeAppliedForRequestId = focus.requestId;
    consumedFocusRequestIds.add(focus.requestId);
    mode = focus.mode;
  }

  async function refresh(forceRefresh = false) {
    // Conserva el modo pedido por el handoff en lugar de volver a live_map (GUA-20261021-7).
    await onLoadWorkspace({ mode, forceRefresh });
  }

  onMount(() => {
    if (!workspace) void refresh(false);
  });
</script>

<section class="view">
  <article class="panel is-flush map-panel">
    <MaritimeMap
      bind:is3D={map3D}
      positions={workspace?.positions ?? []}
      vessels={workspace?.vessels ?? []}
      ports={workspace?.ports ?? []}
      chokepoints={workspace?.chokepoints ?? []}
      chokepointSummaries={workspace?.chokepoint_summaries ?? []}
      flowSummaries={workspace?.flow_summaries ?? []}
      tracks={workspace?.tracks ?? []}
      watchlists={workspace?.watchlists ?? []}
      eventWindows={workspace?.event_windows ?? []}
      coverage={workspace?.coverage ?? null}
      warnings={workspace?.warnings ?? []}
      {loading}
      {focus}
      onRefresh={refresh}
      connected={workspace?.coverage?.coverage_status === "live" || workspace?.coverage?.coverage_status === "partial"}
    />
  </article>
</section>

<style>
  .view {
    height: calc(100vh - 5rem);
    min-height: 38rem;
    display: grid;
    overflow: hidden;
  }

  .map-panel {
    min-height: 0;
    padding: 0;
    overflow: hidden;
  }

  @media (max-width: 760px) {
    .view {
      height: calc(100vh - 4.5rem);
      min-height: 32rem;
    }
  }
</style>
