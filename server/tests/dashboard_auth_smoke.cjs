"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("/app/dashboard.js", "utf8");

function dashboard() {
  const nodes = new Map();
  const sockets = [];
  const timers = new Map();
  let nextTimer = 1;
  let fetchImpl = async () => jsonResponse({});
  const storage = new Map();

  function element() {
    return {
      value: "", textContent: "", innerHTML: "", className: "", dataset: {},
      classList: { add() {}, remove() {}, toggle() {} },
      appendChild() {}, remove() {}, addEventListener() {}, setAttribute() {},
    };
  }
  const document = {
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, element());
      return nodes.get(selector);
    },
    querySelectorAll() { return []; },
    addEventListener() {},
    createElement: element,
    documentElement: { setAttribute() {}, removeAttribute() {} },
    body: element(),
  };

  class FakeWebSocket {
    static OPEN = 1;
    static CONNECTING = 0;
    constructor(url) {
      this.url = url;
      this.readyState = FakeWebSocket.CONNECTING;
      this.listeners = new Map();
      this.sent = [];
      sockets.push(this);
    }
    addEventListener(type, callback) { this.listeners.set(type, callback); }
    emit(type, event = {}) { this.listeners.get(type)?.(event); }
    send(data) { this.sent.push(data); }
    close() { this.readyState = 3; this.emit("close", { code: 1000 }); }
  }

  const context = vm.createContext({
    document,
    window: {
      location: { protocol: "http:", host: "localhost:8000" },
      setTimeout(callback) { const id = nextTimer++; timers.set(id, callback); return id; },
      clearTimeout(id) { timers.delete(id); },
      setInterval(callback) { const id = nextTimer++; timers.set(id, callback); return id; },
      clearInterval(id) { timers.delete(id); },
    },
    localStorage: {
      getItem(key) { return storage.get(key) ?? null; },
      setItem(key, value) { storage.set(key, value); },
      removeItem(key) { storage.delete(key); },
    },
    Headers, TextEncoder, btoa, URLSearchParams, WebSocket: FakeWebSocket,
    fetch: (...args) => fetchImpl(...args),
    console,
  });
  vm.runInContext(source, context, { filename: "dashboard.js" });
  // The token switch is under test; remote refreshes are exercised separately.
  vm.runInContext("refreshAll = async () => {}; toast = () => {};", context);
  return {
    context, nodes, sockets, timers, storage,
    node: (id) => document.querySelector(id),
    state: () => vm.runInContext("STATE", context),
    call: (expression) => vm.runInContext(expression, context),
    setFetch: (fn) => { fetchImpl = fn; },
  };
}

function jsonResponse(payload) {
  return {
    ok: true,
    headers: { get: () => "application/json" },
    json: async () => payload,
  };
}

function seedPrivateView(ui) {
  const state = ui.state();
  Object.assign(state, {
    status: { secret: "old status" },
    diagnostics: { secret: "old diagnostics" },
    integrations: { secret: "old integration" },
    integrationHealth: { secret: "old health" },
    memoryFiles: [{ filename: "Private.md" }],
    memoryFile: "Private.md",
    conversations: [{ content: "old conversation" }],
    schedules: [{ title: "old schedule" }],
    logs: ["old log"],
    chat: [{ text: "old chat" }],
    configSnapshot: { secret: "old config" },
    lastChatSignature: "old signature",
  });
  for (const id of ["#memory-editor", "#chat-input", "#schedule-title", "#schedule-description", "#schedule-datetime", "#log-filter"]) {
    ui.node(id).value = `old ${id}`;
  }
  ui.node("#chat-speaker").value = "old speaker";
  ui.node("#speaker-filter").value = "old speaker";
  ui.node("#speaker-filter").innerHTML = '<option value="old speaker">old speaker</option>';
  ui.node("#memory-title").textContent = "Private.md";
  ui.node("#memory-meta").textContent = "old memory size";
  ui.node("#config-json").textContent = "old config";
  ui.node("#conversation-list").innerHTML = "old conversation";
  ui.node("#chat-feed").innerHTML = "old chat";
  ui.node("#logs-view").textContent = "old log";
}

function assertPrivateViewCleared(ui) {
  const state = ui.state();
  for (const key of ["status", "diagnostics", "configSnapshot"]) assert.equal(state[key], null, key);
  for (const key of ["integrations", "integrationHealth"]) assert.equal(Object.keys(state[key]).length, 0, key);
  for (const key of ["memoryFiles", "conversations", "schedules", "logs", "chat"]) assert.equal(state[key].length, 0, key);
  assert.equal(state.lastChatSignature, "");
  for (const id of ["#memory-editor", "#chat-input", "#schedule-title", "#schedule-description", "#schedule-datetime", "#log-filter"]) {
    assert.equal(ui.node(id).value, "", id);
  }
  assert.equal(ui.node("#chat-speaker").value, "web_user");
  assert.equal(ui.node("#speaker-filter").value, "");
  assert.ok(!ui.node("#speaker-filter").innerHTML.includes("old speaker"));
  for (const id of ["#memory-title", "#memory-meta", "#config-json", "#conversation-list", "#chat-feed", "#logs-view"]) {
    assert.ok(!String(ui.node(id).textContent + ui.node(id).innerHTML).includes("old "), id);
  }
}

async function main() {
  const ui = dashboard();
  seedPrivateView(ui);
  ui.node("#auth-token").value = "한글🔐";
  ui.call("saveToken()");
  assertPrivateViewCleared(ui);
  assert.equal(ui.state().token, "한글🔐");

  let captured;
  ui.setFetch(async (path, options) => {
    captured = { path, options };
    return jsonResponse({ ok: true });
  });
  await ui.call("api('/api/status')");
  const expected = Buffer.from("한글🔐", "utf8").toString("base64url");
  assert.equal(captured.options.headers.get("X-Auth-Token"), expected);
  assert.equal(captured.options.headers.get("X-Auth-Token-Encoding"), "utf8-base64url");
  assert.equal(captured.path, "/api/status");

  ui.call("connectWs(true)");
  const oldSocket = ui.sockets.at(-1);
  assert.equal(oldSocket.url, "ws://localhost:8000/ws");
  oldSocket.readyState = 1;
  oldSocket.emit("open");
  assert.deepEqual(JSON.parse(oldSocket.sent[0]), { event: "authenticate", token: "한글🔐" });

  let releaseOldFetch;
  ui.setFetch(() => new Promise((resolve) => { releaseOldFetch = resolve; }));
  const oldRequest = ui.call("fetchStatus(true)");
  seedPrivateView(ui);
  ui.call("clearToken()");
  assertPrivateViewCleared(ui);
  assert.equal(ui.state().token, "");
  assert.equal(ui.node("#auth-token").value, "");
  const nextSocket = ui.sockets.at(-1);
  assert.notEqual(nextSocket, oldSocket);
  oldSocket.emit("close", { code: 4401 });
  oldSocket.emit("message", { data: JSON.stringify({ event: "log", line: "old private log" }) });
  assert.equal(ui.state().ws, nextSocket);
  assert.equal(ui.state().wsAuthBlocked, false);
  assert.equal(ui.state().logs.length, 0);
  releaseOldFetch(jsonResponse({ mode: "old private status" }));
  await oldRequest.catch(() => {});
  assert.equal(ui.state().status, null);
  assert.ok(!ui.node("#hero-headline").textContent.includes("old private"));

  nextSocket.readyState = 1;
  nextSocket.emit("open");
  assert.deepEqual(JSON.parse(nextSocket.sent[0]), { event: "authenticate", token: "" });
  nextSocket.emit("close", { code: 4401 });
  assert.equal(ui.state().wsAuthBlocked, true);
  assert.equal(ui.state().wsRetry, null);
  assert.equal(ui.state().ws, null);
  ui.call("connectWs()");
  assert.equal(ui.sockets.at(-1), nextSocket);

  // A token change while JSON parsing is pending must also discard the body.
  const parsing = dashboard();
  parsing.node("#auth-token").value = "first";
  parsing.call("saveToken()");
  let releaseBody;
  parsing.setFetch(async () => ({
    ok: true,
    headers: { get: () => "application/json" },
    json: () => new Promise((resolve) => { releaseBody = resolve; }),
  }));
  const parsingRequest = parsing.call("fetchStatus(true)");
  for (let attempt = 0; attempt < 10 && !releaseBody; attempt++) await Promise.resolve();
  assert.equal(typeof releaseBody, "function");
  parsing.node("#auth-token").value = "second";
  parsing.call("saveToken()");
  releaseBody({ mode: "old parsed private status" });
  await parsingRequest;
  assert.equal(parsing.state().status, null);
  console.log("dashboard auth smoke passed");
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
