import "../lib/theme/tokens.css";
import { mount } from "svelte";
import Harness from "./commodity-curves-harness.svelte";
mount(Harness, { target: document.getElementById("app")! });
