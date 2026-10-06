"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { loadModules } = require("./helpers/load-src");

// SERVER used to be a compiled-in constant. It is resolved from Tampermonkey
// storage now, because the server may be a container on another machine
// (docs/DEPLOY.md) whose address cannot be known at compile time. That makes
// the resolution itself worth pinning: getting it wrong points every request
// at the wrong host, and the failure looks like "the server is down".
function load(stored) {
  const GM_getValue = (key, fallback) => (key === "serverUrl" ? stored : fallback);
  return loadModules(["config.js"], ["SERVER", "DEFAULT_SERVER"], { GM_getValue });
}

test("falls back to the local default when nothing is stored", () => {
  // Both shapes Tampermonkey can hand back for a key that was never written.
  for (const unset of [undefined, ""]) {
    const { SERVER, DEFAULT_SERVER } = load(unset);
    assert.equal(SERVER, "http://127.0.0.1:8000");
    assert.equal(SERVER, DEFAULT_SERVER);
  }
});

test("a stored URL wins over the default", () => {
  const { SERVER } = load("http://192.168.1.50:8000");
  assert.equal(SERVER, "http://192.168.1.50:8000");
});

test("a trailing slash is stripped, since every call is SERVER + '/path'", () => {
  // Without this, health() would request http://host:8000//health.
  assert.equal(load("http://192.168.1.50:8000/").SERVER, "http://192.168.1.50:8000");
  assert.equal(load("http://192.168.1.50:8000///").SERVER, "http://192.168.1.50:8000");
});

// The login gate's API token (Settings -> Security) is baked in by the server's
// compiler, never typed: the source ships it empty, and what the compiler does
// with it is pinned in tests/api/test_userscripts.py.
test("the source carries no token, so no credentials are sent to a server with the gate off", () => {
  const GM_getValue = (_key, fallback) => fallback;
  const { SERVER_AUTH, DEFAULT_TOKEN } = loadModules(["config.js"], ["SERVER_AUTH", "DEFAULT_TOKEN"], {
    GM_getValue,
  });
  assert.equal(DEFAULT_TOKEN, "");
  assert.equal(SERVER_AUTH, "");
});
