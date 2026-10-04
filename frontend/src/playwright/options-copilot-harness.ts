import "../lib/theme/tokens.css";
import { mount } from "svelte";
import OptionsCopilotHarness from "./options-copilot-harness.svelte";
mount(OptionsCopilotHarness, { target: document.getElementById("app")! });
