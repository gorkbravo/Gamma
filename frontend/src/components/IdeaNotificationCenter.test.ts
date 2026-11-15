import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import IdeaNotificationCenter from "./IdeaNotificationCenter.svelte";

describe("IdeaNotificationCenter", () => {
  it("counts triggers and reviews due in the top-bar button", () => {
    const body = render(IdeaNotificationCenter, {
      props: {
        notifications: {
          items: [
            {
              notification_id: "trigger:i:c",
              kind: "criterion_triggered",
              idea_id: "i",
              idea_title: "XOM holds",
              created_at: "2026-11-15T09:00:00",
              criterion_id: "c",
              criterion_kind: "invalidate",
              label: "XOM close below 100",
              value_display: "99.00",
              first_met_at: "2026-11-12T00:00:00",
              review_date: null,
              days_overdue: null,
              provenance: null,
            },
            {
              notification_id: "review:i:2026-11-10",
              kind: "review_due",
              idea_id: "i",
              idea_title: "XOM holds",
              created_at: "2026-11-10T00:00:00",
              criterion_id: null,
              criterion_kind: null,
              label: "Review due 2026-11-10",
              value_display: null,
              first_met_at: null,
              review_date: "2026-11-10",
              days_overdue: 5,
              provenance: null,
            },
          ],
          triggered: 1,
          reviews_due: 1,
          evaluation_running: true,
          last_pass: null,
          limitation: "Criteria are evaluated only while Gamma runs.",
          source_provider: "gamma_ideas",
          retrieved_at: "2026-11-15T09:00:00",
          origin: "idea_evaluation.notifications",
        },
      },
    }).body;
    expect(body).toContain('aria-label="Idea notifications: 1 triggered, 1 reviews due"');
    expect(body).toMatch(/class="notice-count[^"]*">2<\/span>/);
    expect(body).toContain("has-triggers");
  });

  it("stays quiet with nothing pending", () => {
    const body = render(IdeaNotificationCenter, { props: { notifications: null } }).body;
    expect(body).toContain('aria-label="Idea notifications: none"');
    expect(body).not.toContain("notice-count");
  });
});
