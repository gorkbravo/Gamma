import "../lib/theme/tokens.css";
import { mount } from "svelte";
import BetaHelpHarness from "./beta-help-harness.svelte";

mount(BetaHelpHarness, {
  target: document.getElementById("app")!
});
