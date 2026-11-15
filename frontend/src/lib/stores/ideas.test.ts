import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  getJson: vi.fn(),
  postJson: vi.fn(),
  patchJson: vi.fn(),
  deleteJson: vi.fn(),
  getText: vi.fn(),
}));

vi.mock("../api/client", () => client);

import {
  acknowledgeCriterion,
  activeIdea,
  addCriterion,
  createIdea,
  evaluateIdea,
  ideaNotifications,
  loadIdeaNotifications,
  deleteIdea,
  exportIdea,
  ideaList,
  ideaOpenRequest,
  ideasError,
  loadIdea,
  pinEvidence,
  pinnableIdeas,
  requestOpenIdea,
  selectedIdeaId,
  transitionIdea,
} from "./ideas";

const LIST = {
  items: [
    { idea_id: "a", title: "Draft idea", status: "draft" },
    { idea_id: "b", title: "Active idea", status: "active" },
    { idea_id: "c", title: "Archived idea", status: "archived" },
  ],
  total: 3,
  status_counts: { draft: 1, active: 1, closed: 0, archived: 1 },
  tags: [],
  storage_warnings: [],
};

describe("ideas store", () => {
  beforeEach(() => {
    Object.values(client).forEach((fn) => fn.mockReset());
    ideaList.set(null);
    activeIdea.set(null);
    selectedIdeaId.set(null);
    ideasError.set("");
    client.getJson.mockImplementation(async (path: string) => (path === "/ideas" ? LIST : { idea_id: path.split("/").pop(), title: "Loaded" }));
  });

  it("offers only drafts and active ideas as pin targets", async () => {
    ideaList.set(LIST as never);
    expect(get(pinnableIdeas).map((item) => item.idea_id)).toEqual(["a", "b"]);
  });

  it("creates an idea and refreshes the board", async () => {
    client.postJson.mockResolvedValue({ idea_id: "n", title: "New" });
    const created = await createIdea({ title: "New", stance: "neutral" });
    expect(created?.idea_id).toBe("n");
    expect(client.postJson).toHaveBeenCalledWith("/ideas", { title: "New", stance: "neutral" });
    expect(get(ideaList)?.total).toBe(3);
  });

  it("pins evidence to the selected idea and updates the open idea", async () => {
    await loadIdea("b");
    expect(get(activeIdea)?.idea_id).toBe("b");
    client.postJson.mockResolvedValue({ idea: { idea_id: "b", title: "Pinned" }, evidence: { evidence_id: "e1" } });
    const draft = { kind: "metric", title: "XOM", captured_values: {}, provenance: null, freshness: null, reopen: null } as const;
    const response = await pinEvidence("b", { ...draft, stance: "challenges", note: "" });
    expect(response?.evidence.evidence_id).toBe("e1");
    expect(client.postJson).toHaveBeenCalledWith("/ideas/b/evidence", expect.objectContaining({ stance: "challenges" }));
    expect(get(activeIdea)?.title).toBe("Pinned");
  });

  it("reports an API failure without throwing", async () => {
    client.postJson.mockRejectedValue(new Error("Evidence stance is required"));
    const result = await transitionIdea("a", "activate");
    expect(result).toBeNull();
    expect(get(ideasError)).toBe("Evidence stance is required");
  });

  it("clears the open idea when it is deleted and exports through the backend renderer", async () => {
    await loadIdea("a");
    client.deleteJson.mockResolvedValue({ success: true });
    expect(await deleteIdea("a")).toBe(true);
    expect(get(activeIdea)).toBeNull();
    expect(get(selectedIdeaId)).toBeNull();

    client.getText.mockResolvedValue("# Idea");
    expect(await exportIdea("b", "md")).toBe("# Idea");
    expect(client.getText).toHaveBeenCalledWith("/ideas/b/export?format=md");
  });

  it("adds a criterion, then refreshes the board and the notifications", async () => {
    await loadIdea("a");
    client.postJson.mockResolvedValue({ idea: { idea_id: "a", title: "With criterion" }, criterion: { criterion_id: "c" } });
    client.getJson.mockImplementation(async (path: string) =>
      path === "/ideas" ? LIST : path === "/ideas/notifications" ? { items: [], triggered: 0, reviews_due: 0 } : { idea_id: "a" }
    );
    const response = await addCriterion("a", {
      kind: "invalidate",
      observable: { observable_id: "equity_close", params: { symbol: "XOM" }, label: "XOM close" },
      condition: "below",
      threshold: 100,
      window: null,
      cadence: "daily_close",
      label: null,
    });
    expect(response?.criterion.criterion_id).toBe("c");
    expect(get(activeIdea)?.title).toBe("With criterion");
    expect(client.getJson).toHaveBeenCalledWith("/ideas/notifications");
  });

  it("evaluates on open with the open trigger and acknowledges through the criterion route", async () => {
    client.postJson.mockResolvedValue({ idea_id: "b" });
    await evaluateIdea("b", "open");
    expect(client.postJson).toHaveBeenCalledWith("/ideas/b/evaluate?trigger=open", {});
    await acknowledgeCriterion("b", "c1");
    expect(client.postJson).toHaveBeenCalledWith("/ideas/b/criteria/c1/acknowledge", {});
  });

  it("loads notifications quietly, without touching the Ideas error line", async () => {
    client.getJson.mockRejectedValue(new Error("backend starting"));
    expect(await loadIdeaNotifications()).toBeNull();
    expect(get(ideasError)).toBe("");
    client.getJson.mockResolvedValue({ items: [], triggered: 2, reviews_due: 0 });
    await loadIdeaNotifications();
    expect(get(ideaNotifications)?.triggered).toBe(2);
  });

  it("issues a fresh open request each time", () => {
    requestOpenIdea("a");
    const first = get(ideaOpenRequest);
    requestOpenIdea("a");
    const second = get(ideaOpenRequest);
    expect(first?.ideaId).toBe("a");
    expect(second?.nonce).toBeGreaterThan(first?.nonce ?? 0);
  });
});
