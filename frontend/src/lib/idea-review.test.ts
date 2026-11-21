import { describe, expect, it } from "vitest";
import {
  closeDraftError,
  closePayload,
  formatHoldingDays,
  outcomeTone,
  reviewKpis,
  shareText,
  verdictTone,
  type CloseDraft,
} from "./idea-review";

function draft(overrides: Partial<CloseDraft> = {}): CloseDraft {
  return { outcome: "confirmed", expected: "Thesis", realizedNote: "", lesson: "Stated exits work.", verdicts: {}, ...overrides };
}

describe("close form", () => {
  it("needs an outcome and a lesson before the idea can close", () => {
    expect(closeDraftError(draft({ outcome: null }))).toBe("Choose an outcome.");
    expect(closeDraftError(draft({ lesson: " ok " }))).toBe("Write the lesson: closing needs a review.");
    expect(closeDraftError(draft())).toBe("");
    expect(closePayload(draft({ outcome: null }))).toBeNull();
  });

  it("sends trimmed text, drops blank verdicts and lets a blank expectation fall back to the thesis", () => {
    expect(
      closePayload(draft({ expected: "  ", realizedNote: " Beat. ", lesson: "  Keep the rule. ", verdicts: { a: "held", b: "" } }))
    ).toEqual({
      outcome: "confirmed",
      lesson: "Keep the rule.",
      expected: null,
      realized_note: "Beat.",
      evidence_verdicts: { a: "held" },
    });
  });
});

describe("review formatting", () => {
  it("formats holding time and shares with their sample", () => {
    expect(formatHoldingDays(0.4)).toBe("Under a day");
    expect(formatHoldingDays(1.2)).toBe("1 day");
    expect(formatHoldingDays(11.6)).toBe("12 days");
    expect(formatHoldingDays(null)).toBe("N/A");
    expect(shareText(1, 2)).toBe("1 of 2 (50%)");
    expect(shareText(0, 0)).toBe("None");
  });

  it("colours outcomes and verdicts as states, not scores", () => {
    expect(outcomeTone("confirmed")).toBe("positive");
    expect(outcomeTone("invalidated")).toBe("negative");
    expect(outcomeTone("abandoned")).toBe("");
    expect(verdictTone("failed")).toBe("negative");
    expect(verdictTone("unclear")).toBe("");
    expect(reviewKpis(null)).toEqual({ reviewed: 0, confirmed: 0, invalidated: 0, abandoned: 0, expired: 0 });
  });
});
