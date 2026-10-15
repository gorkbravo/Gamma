import "../lib/theme/tokens.css";
import { mount } from "svelte";
import Harness from "./script-analytics-harness.svelte";
mount(Harness, { target: document.getElementById("app")! });
