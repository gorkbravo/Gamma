import { createRawSnippet } from "svelte";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import Shell from "./Shell.svelte";
import ViewErrorBoundary from "./ViewErrorBoundary.svelte";

// Simula una vista que revienta al renderizar, como el `each_key_duplicate` de
// Strategy Lab que dejaba la navegación del shell muerta (GUA-20261021-1).
const throwingView = createRawSnippet(() => ({
  render: () => {
    throw new Error("each_key_duplicate: duplicate key 'draft-leg-4' at indexes 0 and 3");
  }
}));

const healthyView = createRawSnippet(() => ({
  render: () => "<p>Strategy Lab composer</p>"
}));

// En SSR, `<svelte:boundary>` solo pinta `failed` si el render recibe `transformError`.
const keepError = (error: unknown) => error;

describe("ViewErrorBoundary", () => {
  it("renders the inline fallback with the error message and a Retry when the view throws", () => {
    const { body } = render(ViewErrorBoundary, {
      props: { resetKey: "strategy_lab", children: throwingView },
      transformError: keepError
    });

    expect(body).toContain("This view failed to render");
    expect(body).toContain("each_key_duplicate: duplicate key 'draft-leg-4' at indexes 0 and 3");
    expect(body).toContain(">Retry</button>");
    expect(body).toContain('role="alert"');
  });

  it("renders the view untouched when nothing throws", () => {
    const { body } = render(ViewErrorBoundary, {
      props: { resetKey: "strategy_lab", children: healthyView },
      transformError: keepError
    });

    expect(body).toContain("<p>Strategy Lab composer</p>");
    expect(body).not.toContain("failed to render");
  });

  it("keeps the Shell topbar (navigation toggle, tab search, Copilot) when the workspace throws", () => {
    // Así pasa Svelte 5 el contenido del slot por defecto a un componente en modo legacy.
    const { body } = render(Shell, {
      props: { activeTab: "strategy_lab", tabs: [], children: throwingView, $$slots: { default: true } } as never,
      transformError: keepError
    });

    expect(body).toContain('aria-label="Toggle navigation"');
    expect(body).toContain("Search tabs");
    expect(body).toContain("Copilot");
    expect(body).toContain("This workspace failed to render");
  });
});
