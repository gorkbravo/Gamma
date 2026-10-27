<script lang="ts">
  // Texto de Copilot con tablas y listas Markdown renderizadas (GUA-20261021-13).
  // Todo se pinta con plantillas escapadas; el modelo nunca inyecta HTML.
  import { isNumericCell, parseCopilotRichText, type CopilotTextSegment } from "../lib/copilot-text";

  export let text: string | null | undefined = "";
  export let emphasis = false;

  let segments: CopilotTextSegment[] = [];
  $: segments = parseCopilotRichText(text);
</script>

{#each segments as segment, segmentIndex (segmentIndex)}
  {#if segment.kind === "paragraph"}
    <p class="rich-paragraph" class:emphasis>{segment.text}</p>
  {:else if segment.kind === "list"}
    {#if segment.ordered}
      <ol class="rich-list">{#each segment.items as item}<li>{item}</li>{/each}</ol>
    {:else}
      <ul class="rich-list">{#each segment.items as item}<li>{item}</li>{/each}</ul>
    {/if}
  {:else if segment.kind === "table"}
    <div class="rich-table-wrap">
      <table class="rich-table">
        <thead>
          <tr>
            {#each segment.header as cell, column}
              <th class:num={segment.align[column] === "right"} class:center={segment.align[column] === "center"}>{cell}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each segment.rows as row}
            <tr>
              {#each row as cell, column}
                <td
                  class:num={segment.align[column] === "right" || (segment.align[column] == null && isNumericCell(cell))}
                  class:center={segment.align[column] === "center"}
                >{cell}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
{/each}

<style>
  .rich-paragraph {
    margin: 0;
    color: var(--text-1);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    white-space: pre-line;
    overflow-wrap: anywhere;
  }

  .rich-paragraph + .rich-paragraph,
  .rich-paragraph + .rich-list,
  .rich-list + .rich-paragraph,
  .rich-table-wrap + .rich-paragraph,
  .rich-paragraph + .rich-table-wrap {
    margin-top: var(--space-2);
  }

  .rich-paragraph.emphasis {
    color: var(--text-0);
  }

  .rich-list {
    margin: 0;
    padding-left: var(--space-5);
    color: var(--text-1);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
  }

  .rich-table-wrap {
    overflow-x: auto;
  }

  .rich-table {
    width: auto;
    min-width: 50%;
    border-collapse: collapse;
    font-size: var(--text-sm);
    font-variant-numeric: tabular-nums;
  }

  .rich-table th,
  .rich-table td {
    padding: var(--space-1) var(--space-3);
    border: 1px solid var(--divider);
    text-align: left;
    vertical-align: top;
    white-space: nowrap;
  }

  .rich-table th {
    color: var(--text-2);
    background: var(--surface-1);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
  }

  .rich-table td {
    color: var(--text-1);
  }

  .rich-table .num {
    text-align: right;
  }

  .rich-table .center {
    text-align: center;
  }
</style>
