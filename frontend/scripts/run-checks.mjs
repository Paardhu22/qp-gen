/**
 * Runs every `scripts/test-*.mjs` self-check in turn — `npm test`.
 * A failing check does not stop the run, so one broken check cannot hide
 * another; the exit code is non-zero if any failed.
 */
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const dir = fileURLToPath(new URL(".", import.meta.url));
const checks = readdirSync(dir).filter((f) => /^test-.*\.mjs$/.test(f)).sort();

const failed = [];
for (const check of checks) {
  const run = spawnSync(process.execPath, [join(dir, check)], { encoding: "utf8" });
  const ok = run.status === 0;
  console.log(`${ok ? "PASS" : "FAIL"}  ${check}`);
  if (!ok) {
    failed.push(check);
    console.log((run.stdout + run.stderr).trim().split("\n").map((l) => "      " + l).join("\n"));
  }
}

console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`);
process.exit(failed.length ? 1 : 0);
