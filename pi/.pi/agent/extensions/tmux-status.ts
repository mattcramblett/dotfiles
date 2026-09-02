import type {
  ExtensionAPI,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";

type Status = "idle" | "working" | "needs-you";

export default function (pi: ExtensionAPI) {
  const pane = process.env.TMUX_PANE;

  if (!pane) return;

  const targetPane = pane;

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
