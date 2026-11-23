import assert from "node:assert/strict";
import { homedir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import extension from "../pi/.pi/agent/extensions/tmux-status.ts";

function setup() {
  const handlers = new Map();
  const calls = [];
  let failure = false;
  const previousPane = process.env.TMUX_PANE;
  process.env.TMUX_PANE = "%7";
  try {
    extension({
      on(name, handler) { handlers.set(name, handler); },
      async exec(command, args, options) {
        calls.push({ command, args, options });
        if (command !== "tmux" && failure) throw new Error("tracker unavailable");
        return { code: 0, stdout: "", stderr: "", killed: false };
      },
    });
  } finally {
    if (previousPane === undefined) delete process.env.TMUX_PANE;
    else process.env.TMUX_PANE = previousPane;
  }
  const session = { cwd: "/original/repo", id: "session-one", file: "/saved/session one.jsonl" };
  const context = {
    mode: "tui", cwd: session.cwd, isIdle: () => true,
    sessionManager: {
      getCwd: () => session.cwd,
      getSessionId: () => session.id,
      getSessionFile: () => session.file,
      getSessionName: () => "task-name",
    },
  };
  return {
    calls, session, context,
    fail(value) { failure = value; },
    emit: (name, event = {}) => handlers.get(name)(event, context),
    records: () => calls.filter(call => call.command !== "tmux"),
  };
}

test("publishes exact session reference and original cwd with the pane ID", async () => {
  const state = setup();
  await state.emit("session_start");
  assert.deepEqual(state.records()[0], {
    command: join(homedir(), ".local/bin/wt-workspace"),
    args: ["remember-conversation", "pi", "--pane", "%7", "--cwd", "/original/repo",
      "--session-id", "session-one", "--session-file", "/saved/session one.jsonl"],
    options: { timeout: 3000 },
  });
  await state.emit("agent_start");
  await state.emit("agent_settled");
  assert.equal(state.records().length, 1);
});

test("new, resumed, and forked sessions replace the captured reference", async () => {
  const state = setup();
  await state.emit("session_start");
  for (const id of ["session-new", "session-resumed", "session-forked"]) {
    state.session.id = id;
    state.session.file = `/saved/${id}.jsonl`;
    await state.emit("session_start");
    assert.ok(state.records().at(-1).args.includes(id));
    assert.ok(state.records().at(-1).args.includes(state.session.file));
  }
  assert.equal(state.records().length, 4);
});

test("ephemeral sessions clear a previous persistent conversation", async () => {
  const state = setup();
  await state.emit("session_start");
  state.session.id = "ephemeral";
  state.session.file = undefined;
  await state.emit("session_start");
  assert.ok(state.records().at(-1).args.includes("ephemeral"));
  assert.ok(!state.records().at(-1).args.includes("--session-file"));
});

test("tracker failure is retried without interrupting status reporting", async () => {
  const state = setup();
  state.fail(true);
  await state.emit("session_start");
  state.fail(false);
  await state.emit("agent_start");
  assert.equal(state.records().length, 2);
  assert.ok(state.calls.some(call => call.command === "tmux" && call.args.includes("working")));
});

test("non-interactive workers do not replace the parent pane conversation", async () => {
  const state = setup();
  state.context.mode = "json";
  await state.emit("session_start");
  await state.emit("agent_start");
  assert.equal(state.records().length, 0);
});

test("shutdown leaves conversation metadata available for recovery", async () => {
  const state = setup();
  await state.emit("session_start");
  await state.emit("session_shutdown");
  assert.ok(!state.calls.some(call => call.args.includes("@worktree_conversation") && call.args.includes("-u")));
});
