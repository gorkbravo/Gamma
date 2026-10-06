import "../lib/theme/tokens.css";
import { mount } from "svelte";
import Harness from "./strategy-experiments-harness.svelte";
mount(Harness, { target: document.getElementById("app")! });
