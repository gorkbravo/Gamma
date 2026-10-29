import "./lib/theme/tokens.css";
import { mount } from "svelte";
import App from "./App.svelte";
import { initAppearance } from "./lib/stores/appearance";

initAppearance();

const app = mount(App, {
  target: document.getElementById("app")!
});

export default app;
