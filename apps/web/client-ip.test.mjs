// node --test apps/web/client-ip.test.mjs   (Node 23.6+ strips the TypeScript types itself)
import assert from "node:assert/strict";
import test from "node:test";

import { forwardedClientIp } from "./lib/server/client-ip.ts";

function request(headers) {
  return new Request("https://app.example/api/auth/login", { headers });
}

test("without CLIENT_IP_HEADER the rightmost X-Forwarded-For entry is the visitor", () => {
  delete process.env.CLIENT_IP_HEADER;
  assert.equal(forwardedClientIp(request({ "x-forwarded-for": "6.6.6.6, 203.0.113.7" })), "203.0.113.7");
  assert.equal(forwardedClientIp(request({})), "");
});

test("with CLIENT_IP_HEADER the named header wins and a spoofed X-Forwarded-For is ignored", () => {
  process.env.CLIENT_IP_HEADER = "CF-Connecting-IP";
  try {
    const visitor = request({ "x-forwarded-for": "6.6.6.6, 104.22.17.40", "cf-connecting-ip": "203.0.113.7" });
    assert.equal(forwardedClientIp(visitor), "203.0.113.7");
    assert.equal(forwardedClientIp(request({ "x-forwarded-for": "6.6.6.6" })), "");
  } finally {
    delete process.env.CLIENT_IP_HEADER;
  }
});
