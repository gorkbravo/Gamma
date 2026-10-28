<script lang="ts">
  import { evidenceLabel, evidenceValue } from "../lib/retained-evidence";
  export let value: unknown;
  export let depth = 0;
  $: entries = value && typeof value === "object" ? Object.entries(value) : [];
  $: scalars = entries.filter(([, v]) => v === null || typeof v !== "object");
  $: groups = entries.filter(([, v]) => v !== null && typeof v === "object");
</script>
{#if value == null}<p>N/A</p>
{:else if typeof value !== "object"}<p>{evidenceValue(value)}</p>
{:else if entries.length === 0}<p>No retained rows.</p>
{:else}
  {#if scalars.length}
    <table class="data-table is-keyvalue"><tbody>{#each scalars as [key, item]}<tr><th scope="row">{evidenceLabel(key)}</th><td>{evidenceValue(item, key)}</td></tr>{/each}</tbody></table>
  {/if}
  {#each groups as [key, item]}
    <details open={depth === 0}><summary>{Array.isArray(value) ? `Observation ${Number(key) + 1}` : evidenceLabel(key)}</summary>
      <svelte:self value={item} depth={depth + 1} />
    </details>
  {/each}
{/if}
<style>
  /* The label/value rows are .data-table.is-keyvalue in primitives.css. */
  summary { padding: var(--space-3) var(--space-5); cursor: pointer; font-family: var(--display-font); font-size: var(--text-sm); }
  summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  p { padding: var(--space-3) var(--space-5); font-size: var(--text-xs); color: var(--text-2); }
</style>
