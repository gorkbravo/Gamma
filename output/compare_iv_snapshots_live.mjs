import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const root = process.cwd();
const require = createRequire(path.join(root, "frontend", "package.json"));
const { build } = require("esbuild");
const bundle = await build({ entryPoints: [path.join(root, "frontend/src/lib/iv-snapshots.ts")],
  bundle: true, write: false, platform: "node", format: "cjs", define: { "import.meta.env": "{}" } });
const module = { exports: {} };
new Function("module", "exports", "require", bundle.outputFiles[0].text)(module, module.exports, require);
const directory = path.join(root, "output/iv-snapshots-live-2026-10-06");
const before = JSON.parse(fs.readFileSync(path.join(directory, "capture-1.json"))).surface;
const after = JSON.parse(fs.readFileSync(path.join(directory, "capture-2.json"))).surface;
const comparison = module.exports.compareIvSnapshots(before, after);
if (!comparison.rows.length || !comparison.rows.some((row) => row.change != null)) throw new Error("No exact observed live comparison could be computed.");
const result = { before: before.timestamp, after: after.timestamp, source_provider: before.source_provider,
  common_expiries: comparison.rows.length, observed_iv_changes: comparison.rows.filter((row) => row.change != null).length,
  ...comparison };
fs.writeFileSync(path.join(directory, "comparison.json"), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
