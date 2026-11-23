import { homedir } from "node:os";
import { join } from "node:path";
import type {
  ExtensionAPI,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";

type Status = "idle" | "working" | "needs-you";

export default function (pi: ExtensionAPI) {
  const pane = process.env.TMUX_PANE;

  if (!pane) return;

  const targetPane = pane;
  let publishedConversation: string | undefined;

  async function publishConversation(ctx: ExtensionContext) {
    if (ctx.mode !== "tui") return;

    const args = [
      "remember-conversation", "pi", "--pane", targetPane,
      "--cwd", ctx.sessionManager.getCwd(),
      "--session-id", ctx.sessionManager.getSessionId(),
    ];
    const sessionFile = ctx.sessionManager.getSessionFile();
    if (sessionFile) args.push("--session-file", sessionFile);
    const signature = JSON.stringify(args);
    if (signature === publishedConversation) return;

    try {
      const result = await pi.exec(join(homedir(), ".local/bin/wt-workspace"), args, {
        timeout: 3000,
      });
      if (result.code === 0) publishedConversation = signature;
    } catch {
      // Workspace tracking must never interrupt Pi.
    }
  }

  async function setOption(name: string, value: string) {
    await pi.exec("tmux", ["set-option", "-p", "-t", targetPane, name, value], {
      timeout: 1000,
    });
  }

  async function unsetOption(name: string) {
    await pi.exec("tmux", ["set-option", "-p", "-u", "-t", targetPane, name], {
      timeout: 1000,
    });
  }

  async function publish(status: Status, ctx: ExtensionContext) {
    try {
      await Promise.all([
        publishConversation(ctx),
        setOption("@pi_status", status),
        setOption("@pi_cwd", ctx.cwd),
        setOption("@pi_updated_at", String(Date.now())),
        setOption("@pi_pid", String(process.pid)),
      ]);
    } catch {
      // Status reporting must never interrupt Pi.
    }
  }

  async function publishName(name: string | undefined) {
    try {
      if (name) {
        await setOption("@pi_name", name);
      } else {
        await unsetOption("@pi_name");
      }
    } catch {
      // Status reporting must never interrupt Pi.
    }
  }

  pi.on("session_start", async (_event, ctx) => {
    await Promise.all([
      publish("idle", ctx),
      publishName(ctx.sessionManager.getSessionName()),
    ]);
  });

  pi.on("agent_start", async (_event, ctx) => {
    await publish("working", ctx);
  });

  pi.on("agent_settled", async (_event, ctx) => {
    await publish("idle", ctx);
  });

  pi.on("ui_prompt_start", async (_event, ctx) => {
    await publish("needs-you", ctx);
  });

  pi.on("ui_prompt_end", async (_event, ctx) => {
    await publish(ctx.isIdle() ? "idle" : "working", ctx);
  });

  pi.on("session_info_changed", async (event) => {
    await publishName(event.name);
  });

  pi.on("session_shutdown", async () => {
    try {
      await Promise.all([
        unsetOption("@pi_status"),
        unsetOption("@pi_cwd"),
        unsetOption("@pi_updated_at"),
        unsetOption("@pi_pid"),
        unsetOption("@pi_name"),
      ]);
    } catch {
      // The tmux pane may already be closing.
    }
  });
}
