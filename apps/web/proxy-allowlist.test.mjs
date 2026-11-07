import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const source = readFileSync(
  fileURLToPath(new URL("./app/api/portal/[token]/[[...path]]/route.ts", import.meta.url)),
  "utf8",
);

test("portal proxy allows the certificate download", () => {
  const match = source.match(/GET: new Set\(\[([\s\S]*?)\]\)/);
  assert.ok(match);
  const names = [...match[1].matchAll(/"([^"]*)"/g)].map((item) => item[1]);
  assert.deepEqual(names, ["", "preview", "signed-document", "certificate"]);
});
