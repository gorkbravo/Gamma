<script lang="ts">
  import { basicSetup } from "codemirror";
  import { Compartment, EditorState } from "@codemirror/state";
  import { EditorView } from "@codemirror/view";
  import { python } from "@codemirror/lang-python";
  import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
  import { tags } from "@lezer/highlight";
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
      // B′: the editor is a tinted inset like a field (the syntax colours
      // are AA on the tint, contrast.test.ts).
      backgroundColor: "var(--tint)",
      fontSize: "var(--text-sm)"
    },
    ".cm-content": {
      caretColor: "var(--accent)",
      fontFamily: "var(--font-code), monospace",
      padding: "var(--space-3) 0"
    },
    ".cm-scroller": { overflow: "auto" },
    ".cm-gutters": {
      color: "var(--text-2)",
      backgroundColor: "var(--tint)",
      borderRight: "1px solid var(--divider)"
    },
    // The hover tint: 6% of the accent in dark, 4% in light, so comments
    // keep 4.5:1 on the active line.
    ".cm-activeLine, .cm-activeLineGutter": {
      backgroundColor: "var(--hover-bg)"
    },
    ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
      backgroundColor: "color-mix(in srgb, var(--accent) 24%, transparent) !important"
    },
    "&.cm-focused": { outline: "1px solid var(--accent)", outlineOffset: "-1px" }
  });

  /* Syntax colours come from the tokens, so they follow the theme and reach
     WCAG AA on the editor background. CodeMirror's default style is made
     for a light background and fell to 2.6:1 on the dark one. */
  const highlight = HighlightStyle.define([
    { tag: [tags.comment, tags.lineComment, tags.blockComment], color: "var(--text-2)" },
    { tag: [tags.string, tags.special(tags.string)], color: "var(--positive)" },
    { tag: [tags.keyword, tags.controlKeyword, tags.definitionKeyword, tags.operatorKeyword, tags.moduleKeyword, tags.self], color: "var(--accent)" },
    { tag: [tags.number, tags.bool, tags.null], color: "var(--warning)" },
    { tag: [tags.function(tags.variableName), tags.function(tags.propertyName), tags.definition(tags.variableName), tags.className], color: "var(--text-0)" },
    { tag: tags.invalid, color: "var(--negative)" }
  ]);

  onMount(() => {
    view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: value,
        extensions: [
          basicSetup,
          python(),
          syntaxHighlighting(highlight),
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
    border: 1px solid transparent;
    background: var(--tint);
    overflow: hidden;
    border-radius: var(--panel-radius);
  }

  .code-editor.disabled {
    opacity: 0.68;
  }

  :global(.code-editor .cm-editor) {
    height: 100%;
  }
</style>
