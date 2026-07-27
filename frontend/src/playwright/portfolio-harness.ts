import "../lib/theme/tokens.css";
import { mount } from "svelte";
import PortfolioHarness from "./portfolio-harness.svelte";

declare global {
  interface Window {
    __gammaPortfolioEvents: Array<{ type: string; payload: unknown }>;
  }
}

window.__gammaPortfolioEvents = [];

mount(PortfolioHarness, {
  target: document.getElementById("app")!
});
