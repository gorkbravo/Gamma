import "../lib/theme/tokens.css";
import { mount } from "svelte";
import CopilotRecoveryHarness from "./copilot-recovery-harness.svelte";
mount(CopilotRecoveryHarness, { target: document.getElementById("app")! });
