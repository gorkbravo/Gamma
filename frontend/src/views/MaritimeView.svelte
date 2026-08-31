<script lang="ts">
  import { onMount } from "svelte";
  import MaritimeMap from "../components/MaritimeMap.svelte";
  import type { MaritimeMode, MaritimeWorkspaceResponse } from "../lib/api/types";
  import type { MaritimeLoadOptions } from "../lib/stores/app";

  export let workspace: MaritimeWorkspaceResponse | null = null;
  export let loading = false;
  export let mode: MaritimeMode = "live_map";
  export let onLoadWorkspace: (options?: MaritimeLoadOptions) => Promise<unknown> | void;
  export let focusChokepointId: string | null = null;

  let map3D = false;

  async function refresh(forceRefresh = false) {
    mode = "live_map";
    await onLoadWorkspace({ mode: "live_map", forceRefresh });
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
      {focusChokepointId}
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
