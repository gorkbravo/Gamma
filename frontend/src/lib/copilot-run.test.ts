import { describe, expect, it } from "vitest";
import type { CopilotRunEvent } from "./api/types";
import { createCopilotRunState, isTerminalCopilotRunEvent, reduceCopilotRunEvent } from "./copilot-run";

function event(partial: Partial<CopilotRunEvent> & { sequence: number; event: string }): CopilotRunEvent {
  return {
    run_id: "run_test",
    timestamp: "2026-07-14T00:00:00Z",
    data: {},
    result: null,
    ...partial
  };
}

describe("reduceCopilotRunEvent", () => {
  it("accumulates deltas, tools, usage, and completes with the final result", () => {
    let state = createCopilotRunState("run_test");
    state = reduceCopilotRunEvent(
      state,
      event({ sequence: 0, event: "run.created", data: { domain: "macro", provider: "mock", model: "m1" } })
    );
    expect(state.phase).toBe("streaming");
    expect(state.provider).toBe("mock");

    state = reduceCopilotRunEvent(state, event({ sequence: 1, event: "tool.call", data: { tool_name: "get_macro" } }));
    expect(state.toolNotes).toEqual([{ toolName: "get_macro", state: "running", summary: null, sourceIds: [] }]);

    state = reduceCopilotRunEvent(
      state,
      event({
        sequence: 2,
        event: "tool.result",
        data: { tool_name: "get_macro", summary: "Loaded", source_ids: ["macro.snapshot"] }
      })
    );
    expect(state.toolNotes).toEqual([
      { toolName: "get_macro", state: "done", summary: "Loaded", sourceIds: ["macro.snapshot"] }
    ]);

    state = reduceCopilotRunEvent(state, event({ sequence: 3, event: "text.delta", data: { delta: "Hello " } }));
    state = reduceCopilotRunEvent(state, event({ sequence: 4, event: "text.delta", data: { delta: "world" } }));
    expect(state.provisionalText).toBe("Hello world");

    state = reduceCopilotRunEvent(
      state,
      event({ sequence: 5, event: "usage", data: { input_tokens: 10, output_tokens: 3 } })
    );
    expect(state.usage).toEqual({ input_tokens: 10, output_tokens: 3 });

    const completion = event({ sequence: 6, event: "completed", data: { status: "ready" }, result: { status: "ready" } });
    expect(isTerminalCopilotRunEvent(completion)).toBe(true);
    state = reduceCopilotRunEvent(state, completion);
    expect(state.phase).toBe("completed");
    expect(state.terminalEvent).toBe("completed");
    expect(state.rawResult).toEqual({ status: "ready" });
  });

  it("drops stale, duplicate, and foreign-run events", () => {
    let state = createCopilotRunState("run_test");
    state = reduceCopilotRunEvent(state, event({ sequence: 0, event: "run.created" }));
    state = reduceCopilotRunEvent(state, event({ sequence: 1, event: "text.delta", data: { delta: "a" } }));

    const duplicate = reduceCopilotRunEvent(state, event({ sequence: 1, event: "text.delta", data: { delta: "a" } }));
    expect(duplicate).toBe(state);

    const stale = reduceCopilotRunEvent(state, event({ sequence: 0, event: "text.delta", data: { delta: "x" } }));
    expect(stale).toBe(state);

    const foreign = reduceCopilotRunEvent(
      state,
      event({ sequence: 2, event: "text.delta", data: { delta: "z" }, run_id: "run_other" })
    );
    expect(foreign).toBe(state);
  });

  it("keeps the first terminal event and ignores anything after it", () => {
    let state = createCopilotRunState("run_test");
    state = reduceCopilotRunEvent(state, event({ sequence: 0, event: "run.created" }));
    state = reduceCopilotRunEvent(
      state,
      event({ sequence: 1, event: "cancelled", data: { reason: "user_cancelled" }, result: { status: "cancelled" } })
    );
    expect(state.phase).toBe("cancelled");
    expect(state.statusDetail).toBe("Copilot run cancelled.");

    const afterTerminal = reduceCopilotRunEvent(
      state,
      event({ sequence: 2, event: "completed", data: {}, result: { status: "ready" } })
    );
    expect(afterTerminal).toBe(state);
  });

  it("records refusal and incomplete detail as typed status text", () => {
    let state = createCopilotRunState("run_test");
    state = reduceCopilotRunEvent(state, event({ sequence: 0, event: "run.created" }));
    state = reduceCopilotRunEvent(state, event({ sequence: 1, event: "refusal", data: { message: "Cannot help." } }));
    expect(state.statusDetail).toBe("Cannot help.");

    state = reduceCopilotRunEvent(
      state,
      event({ sequence: 2, event: "incomplete", data: { reason: "max_output_tokens" } })
    );
    expect(state.statusDetail).toBe("Response ended early: max_output_tokens");

    state = reduceCopilotRunEvent(
      state,
      event({ sequence: 3, event: "failed", data: { message: "Provider transport failed." } })
    );
    expect(state.phase).toBe("failed");
    expect(state.statusDetail).toBe("Provider transport failed.");
  });
});
