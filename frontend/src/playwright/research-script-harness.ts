import "../lib/theme/tokens.css";
import { mount } from "svelte";
import StrategyScriptWorkspace from "../components/StrategyScriptWorkspace.svelte";

mount(StrategyScriptWorkspace, { target: document.getElementById("app")! });
