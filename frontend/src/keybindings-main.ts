import "./lib/theme/tokens.css";
import { mount } from "svelte";
import KeyBindingsWindow from "./KeyBindingsWindow.svelte";
import { initAppearance } from "./lib/stores/appearance";

initAppearance();

const app = mount(KeyBindingsWindow, {
  target: document.getElementById("app")!,
});

export default app;
