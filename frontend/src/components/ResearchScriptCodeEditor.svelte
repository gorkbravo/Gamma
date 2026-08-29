<script lang="ts">
  import { basicSetup } from "codemirror";
  import { Compartment, EditorState } from "@codemirror/state";
  import { EditorView } from "@codemirror/view";
  import { python } from "@codemirror/lang-python";
  import { onDestroy, onMount } from "svelte";

  export let value = "";
  export let disabled = false;
  export let ariaLabel = "Python source";
  export let onChange: (source: string) => void = () => undefined;

  let host: HTMLDivElement;
  let view: EditorView | null = null;
  const editable = new Compartment();
  let applyingExternalValue = false;

  const theme = EditorView.theme({
    "&": {
      height: "100%",
      color: "var(--text-1)",
      backgroundColor: "var(--surface-0)",
      fontSize: "var(--text-sm)"
    },
    ".cm-content": {
      caretColor: "var(--accent)",
      fontFamily: "var(--font-mono)",
      padding: "var(--space-3) 0"
    },
    ".cm-scroller": { overflow: "auto" },
    ".cm-gutters": {
      color: "var(--text-3)",
      backgroundColor: "var(--surface-1)",
      borderRight: "1px solid var(--panel-border)"
    },
    ".cm-activeLine, .cm-activeLineGutter": {
      backgroundColor: "color-mix(in srgb, var(--accent) 6%, transparent)"
    },
    ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
      backgroundColor: "color-mix(in srgb, var(--accent) 24%, transparent) !important"
    },
    "&.cm-focused": { outline: "2px solid color-mix(in srgb, var(--accent) 55%, transparent)" }
  });

  onMount(() => {
    view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: value,
        extensions: [
          basicSetup,
          python(),
          theme,
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({
            "aria-label": ariaLabel,
            "aria-multiline": "true",
            role: "textbox",
            spellcheck: "false"
          }),
          editable.of(EditorView.editable.of(!disabled)),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged || applyingExternalValue) return;
            onChange(update.state.doc.toString());
          })
        ]
      })
    });
  });

  onDestroy(() => view?.destroy());

  $: if (view && value !== view.state.doc.toString()) {
    applyingExternalValue = true;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
    applyingExternalValue = false;
  }

  $: if (view) {
    view.dispatch({ effects: editable.reconfigure(EditorView.editable.of(!disabled)) });
  }
</script>

<div
  bind:this={host}
  class="code-editor"
  class:disabled
  aria-label={`${ariaLabel} editor`}
></div>

<style>
  .code-editor {
    min-height: 24rem;
    height: min(58vh, 46rem);
    border: 1px solid var(--panel-border);
    background: var(--surface-0);
    overflow: hidden;
  }

  .code-editor.disabled {
    opacity: 0.68;
  }

  :global(.code-editor .cm-editor) {
    height: 100%;
  }
</style>
