import "../lib/theme/tokens.css";
import { mount } from "svelte";
import Harness from "./iv-snapshots-harness.svelte";
mount(Harness, { target: document.getElementById("app")! });
