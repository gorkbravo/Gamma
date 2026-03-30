import "./lib/theme/tokens.css";
import { mount } from "svelte";
import KeyBindingsWindow from "./KeyBindingsWindow.svelte";

const app = mount(KeyBindingsWindow, {
  target: document.getElementById("app")!,
});

export default app;
