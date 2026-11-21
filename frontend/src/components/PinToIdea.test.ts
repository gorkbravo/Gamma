import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import PinToIdea from "./PinToIdea.svelte";

describe("PinToIdea", () => {
  it("is disabled with its reason when the panel has nothing to pin", () => {
    const { body } = render(PinToIdea, { props: { draft: null, disabledReason: "Load a surface before pinning it." } });
    expect(body).toContain("Pin to idea");
    expect(body).toContain("disabled");
    expect(body).toContain('title="Load a surface before pinning it."');
  });

  it("names what it would pin when a draft exists", () => {
    const { body } = render(PinToIdea, {
      props: {
        draft: { kind: "metric", title: "SPY options surface", captured_values: {}, provenance: null, freshness: null, reopen: null },
      },
    });
    expect(body).toContain('title="Pin “SPY options surface” to an idea"');
    expect(body).toContain('aria-haspopup="dialog"');
    expect(body).not.toMatch(/<button[^>]*disabled/);
  });
});
