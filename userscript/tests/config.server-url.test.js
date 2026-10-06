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

// The login gate's credentials (Settings -> Security), resolved the same way.
function loadAuth(stored) {
  const GM_getValue = (key, fallback) => (key === "serverLogin" ? stored : fallback);
  return loadModules(["config.js"], ["SERVER_AUTH"], { GM_getValue, btoa, TextEncoder }).SERVER_AUTH;
}

test("no login stored means no credentials, which is what a server with the gate off wants", () => {
  for (const unset of [undefined, "", "no-colon-so-not-a-login"]) {
    assert.equal(loadAuth(unset), "");
  }
});

test("a stored login becomes a Basic header, UTF-8 encoded", () => {
  assert.equal(loadAuth("matt:hunter2"), "Basic " + Buffer.from("matt:hunter2").toString("base64"));
  // btoa alone throws on anything outside Latin-1.
  assert.equal(loadAuth("matt:pässwörd✓"), "Basic " + Buffer.from("matt:pässwörd✓").toString("base64"));
});
