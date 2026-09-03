import "../lib/theme/tokens.css";
import { mount } from "svelte";
import StrategyComposerHarness from "./strategy-composer-harness.svelte";

mount(StrategyComposerHarness, {
  target: document.getElementById("app")!
});
