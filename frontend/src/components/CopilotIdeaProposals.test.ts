import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { CopilotDraftMutation, CopilotResearchCardResult } from "../lib/api/types";
import { normalizeCopilotResearchCardResult } from "../lib/copilot-result";
import { proposalCriteria, proposalLegs, proposalStatusLabel, proposalsForResult } from "../lib/copilot-idea-proposals";
import CopilotIdeaProposals from "./CopilotIdeaProposals.svelte";

const PROPOSAL: CopilotDraftMutation = {
  mutation_id: "mutation-1",
  domain: "ideas",
  tool_id: "ideas.propose_idea_draft",
  action_type: "draft_change",
  target_id: "new_idea",
  target_label: "Oil producers lag crude",
  status: "pending",
  requires_confirmation: true,
  confirmation_token: "confirm-1",
  apply_tool_id: "ideas.apply_idea_draft",
  session_id: "s1",
  proposal_hash: "hash",
  diff: [],
  rendered_diff: ["New draft idea: Oil producers lag crude"],
  proposed_payload: {
    title: "Oil producers lag crude",
    thesis: "XOM underperforms Brent while OPEC adds supply.",
    stance: "relative",
    legs: [
      { entity_type: "equity", symbol: "XOM", label: "Exxon Mobil", weight: -1 },
      { entity_type: "etf", symbol: "USO", label: "US Oil Fund", weight: 1 },
    ],
    criteria: [
      { kind: "invalidate", label: "XOM close up 8.00% or more over 1 month", rationale: "A rally breaks the lag." },
      { kind: "review", label: "Date reached 2026-12-31", rationale: "" },
    ],
  },
  rationale: "The Commodities card shows Brent backwardation widening.",
  warnings: ["Criterion 2 is unavailable right now: Needs Trader Workstation."],
  source_ids: [],
  rollback_snapshot_id: null,
  created_at: "2026-11-23T10:00:00",
  expires_at: "2026-11-23T10:15:00",
  applied_at: null,
  source_provider: "gamma_copilot",
  origin: "copilot_ideas.draft_idea_from_context",
  transformation_note: null,
};

const RESULT = normalizeCopilotResearchCardResult("commodities", {
  domain: "commodities",
  current_tab: "commodities",
  status: "ready",
  provider: "mock",
  card: null,
  proposal_ids: ["mutation-1"],
  proposals: [PROPOSAL],
}) as CopilotResearchCardResult;

describe("copilot idea proposal helpers", () => {
  it("keeps proposals through normalization and reads the payload", () => {
    expect(RESULT.proposal_ids).toEqual(["mutation-1"]);
    expect(RESULT.proposals?.[0].mutation_id).toBe("mutation-1");
    expect(normalizeCopilotResearchCardResult("macro", { status: "ready" }).proposals).toEqual([]);
    expect(proposalsForResult(RESULT, [PROPOSAL, { ...PROPOSAL, mutation_id: "dcf", domain: "fundamentals" }]).map((item) => item.mutation_id)).toEqual(["mutation-1"]);
    expect(proposalLegs(PROPOSAL.proposed_payload)).toBe("XOM -1 · USO +1");
    // GUA-20261124-9: una propuesta guardada con la nota libre del modelo como etiqueta muestra el ticker.
    const stored = { legs: [{ entity_type: "etf", symbol: "USO", label: "Proposed oil ETF proxy; verify tracking error", weight: 1 }] };
    expect(proposalLegs(stored)).toBe("USO +1");
    expect(proposalLegs({ legs: [{ entity_type: "equity", label: "XOM", weight: null }] })).toBe("XOM");
    expect(proposalCriteria(PROPOSAL.proposed_payload)[0]).toEqual({ kind: "Invalidate", label: "XOM close up 8.00% or more over 1 month", rationale: "A rally breaks the lag." });
    expect(proposalStatusLabel("pending")).toBe("Awaiting your decision");
    expect(proposalStatusLabel("applied")).toBe("Draft idea created");
  });
});

describe("CopilotIdeaProposals", () => {
  it("shows a pending draft with its criteria, warnings and the accept and reject actions", () => {
    const { body } = render(CopilotIdeaProposals, { props: { result: RESULT } });
    expect(body).toContain("Drafted idea");
    expect(body).toContain("Awaiting your decision");
    expect(body).toContain("Nothing is created until you accept it");
    expect(body).toContain("XOM underperforms Brent");
    expect(body).toContain("XOM close up 8.00% or more over 1 month");
    expect(body).toContain("Needs Trader Workstation");
    expect(body).toContain("Create draft idea");
    expect(body).toContain("Reject");
  });

  it("offers to open the idea once the draft was created, and no actions after a rejection", () => {
    const applied = { ...RESULT, proposals: [{ ...PROPOSAL, status: "applied", target_id: "idea-9" }] };
    const body = render(CopilotIdeaProposals, { props: { result: applied } }).body;
    expect(body).toContain("Draft idea created");
    expect(body).toContain("Open idea");
    expect(body).not.toContain("Create draft idea");
    const rejected = render(CopilotIdeaProposals, { props: { result: { ...RESULT, proposals: [{ ...PROPOSAL, status: "rejected" }] } } }).body;
    expect(rejected).toContain("Rejected");
    expect(rejected).not.toContain("Open idea");
    expect(rejected).not.toContain("Create draft idea");
  });
});
