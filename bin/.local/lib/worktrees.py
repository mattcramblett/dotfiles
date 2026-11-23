"""Local worktree discovery, preferences, and tmux workspace operations."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


class WorkspaceError(Exception):
    pass


def warn(message):
    print(f"worktrees: {message}", file=sys.stderr)


def run(args, *, check=True):
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except OSError as error:
        raise WorkspaceError(f"Cannot run {args[0]}: {error}") from error
    if check and result.returncode:
        raise WorkspaceError(result.stderr.strip() or f"{args[0]} exited {result.returncode}")
    return result


def output(args):
    return run(args).stdout.removesuffix("\n")


def canonical(path):
    return str(Path(path).expanduser().resolve())


def valid_agent(name):
    return isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", name) is not None


def valid_name(name):
    return isinstance(name, str) and bool(name) and re.search(r"[.:\x00-\x1f\x7f]", name) is None


def valid_conversation(value):
    if not isinstance(value, dict) or value.get("agent") not in ("pi", "claude"):
        return False
    session_id = value.get("session_id")
    if not isinstance(session_id, str):
        return False
    pattern = (r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}" if value["agent"] == "claude"
               else r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
    return re.fullmatch(pattern, session_id) is not None and all(
        isinstance(value.get(key), str) and "\0" not in value[key] and Path(value[key]).is_absolute()
        for key in ("cwd", "session_file")
    )


def repository(path):
    return canonical(output(["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"]))


def git_worktrees(common):
    raw = output(["git", "-C", common, "worktree", "list", "--porcelain", "-z"])
    records = []
    record = {}
    for field in raw.split("\0"):
        if not field:
            if record:
                records.append(record)
                record = {}
        else:
            key, _, value = field.partition(" ")
            record[key] = value
    return records


def identify(path):
    root = canonical(output(["git", "-C", str(path), "rev-parse", "--show-toplevel"]))
    common = repository(root)
    if not any(canonical(item["worktree"]) == root for item in git_worktrees(common) if "worktree" in item):
        raise WorkspaceError(f"Not a registered worktree: {path}")
    return root, common


class Registry:
    def __init__(self):
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
        self.directory = base / "worktrees"
        self.path = self.directory / "registry.json"

    def read(self):
        try:
            with self.path.open() as stream:
                data = json.load(stream)
        except FileNotFoundError:
            return {"version": 1, "repositories": [], "worktrees": {}}
        except (OSError, ValueError) as error:
            raise WorkspaceError(f"Cannot read {self.path}; state preserved: {error}") from error
        if (not isinstance(data, dict) or data.get("version") != 1
                or not isinstance(data.get("repositories"), list)
                or not isinstance(data.get("worktrees"), dict)):
            raise WorkspaceError(f"Invalid registry format at {self.path}; state preserved")
        return data

    def snapshot(self):
        try:
            return self.read()
        except WorkspaceError as error:
            warn(error)
            return {"version": 1, "repositories": [], "worktrees": {}}

    @contextmanager
    def transaction(self):
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with os.fdopen(os.open(self.directory / "registry.lock", os.O_CREAT | os.O_RDWR, 0o600), "a") as lock:
                deadline = time.monotonic() + 2
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise WorkspaceError("Timed out waiting for the registry lock")
                        time.sleep(0.01)
                data = self.read()
                yield data
                with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as stream:
                    temporary = stream.name
                    json.dump(data, stream, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
        except OSError as error:
            raise WorkspaceError(f"Cannot update {self.path}: {error}") from error
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def remember(self, common, path=None, **preferences):
        with self.transaction() as data:
            if common not in data["repositories"]:
                data["repositories"].append(common)
            if path:
                previous = data["worktrees"].get(path, {})
                if not isinstance(previous, dict):
                    warn(f"Invalid metadata for {path}; leaving it unchanged")
                    return
                if "agent" in preferences and preferences["agent"] != previous.get("agent"):
                    previous = {**previous, "conversation": None}
                conversation = preferences.get("conversation")
                if valid_conversation(conversation):
                    for other_path, other in data["worktrees"].items():
                        saved = other.get("conversation") if isinstance(other, dict) else None
                        if other_path != path and isinstance(saved, dict) and all(
                                saved.get(key) == conversation[key] for key in ("agent", "session_id", "session_file")):
                            other["conversation"] = None
                data["worktrees"][path] = {
                    **previous, "repository": common, **preferences, "updated_at": time.time(),
                }


def best_effort(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except WorkspaceError as error:
        warn(error)
        return None


def preferences(data, path, common):
    record = data["worktrees"].get(path, {})
    if (not isinstance(record, dict) or record.get("repository", common) != common
            or ("agent" in record and not valid_agent(record["agent"]))
            or ("session_name" in record and not valid_name(record["session_name"]))
            or not isinstance(record.get("updated_at", 0), (int, float))):
        warn(f"Ignoring invalid metadata for {path}")
        return {}
    if record.get("conversation") is not None and (
            not valid_conversation(record["conversation"]) or record["conversation"]["agent"] != record.get("agent")):
        warn(f"Ignoring invalid conversation metadata for {path}")
        return {**record, "conversation": None}
    return record


class Tmux:
    def call(self, *args):
        return output(["tmux", *args])

    def value(self, target, expression):
        return self.call("display-message", "-p", "-t", target, expression)

    def sessions(self):
        if not shutil.which("tmux"):
            return []
        separator = "\x1f"
        result = run(["tmux", "list-sessions", "-F", separator.join([
            "#{session_id}", "#{session_name}", "#{@worktree_path}", "#{session_path}", "#{session_activity}",
        ])], check=False)
        if result.returncode:
            if not any(message in result.stderr.lower() for message in ("no server", "no such file", "error connecting")):
                warn(result.stderr.strip())
            return []
        sessions = []
        for line in result.stdout.splitlines():
            parts = line.split(separator)
            if len(parts) != 5:
                warn("Ignoring an unreadable tmux session record")
                continue
            session_id, name, tagged, path, activity = parts
            if tagged or path:
                sessions.append({"id": session_id, "name": name, "path": canonical(tagged or path),
                                 "tagged": bool(tagged), "activity": int(activity or 0)})
        return sessions

    def matching(self, path, sessions=None):
        matches = [item for item in (sessions if sessions is not None else self.sessions()) if item["path"] == path]
        return max(matches, key=lambda item: item["activity"], default=None)

    def attach(self, session_id):
        action = "switch-client" if os.environ.get("TMUX") else "attach-session"
        if action == "switch-client":
            self.call(action, "-t", session_id)
        else:
            result = subprocess.run(["tmux", action, "-t", session_id])
            if result.returncode:
                raise WorkspaceError(f"tmux attach-session exited {result.returncode}")


def default_name(path, common):
    trees = git_worktrees(common)
    primary = next((item["worktree"] for item in trees if "worktree" in item and "bare" not in item), path)
    repo_name = Path(primary).name
    branch = output(["git", "-C", path, "branch", "--show-current"])
    configured = run(["git", "-C", path, "config", "--get", "worktree.branchPrefix"], check=False)
    prefix = configured.stdout.strip() or "mattcramblett/"
    label = branch.removeprefix(prefix).replace("/", "-") if branch else Path(path).name
    return re.sub(r"[.:\x00-\x1f\x7f]", "_", f"{repo_name}-{label}")


def remember_session(tmux, registry, session):
    path = tmux.value(session, "#{@worktree_path}")
    if not path:
        return
    path, common = identify(path)
    name = tmux.value(session, "#{session_name}")
    if valid_name(name):
        registry.remember(common, path, session_name=name)


def remember_agent(tmux, registry, agent, path=None, pane=None, conversation=None, cwd=None):
    if not valid_agent(agent):
        raise WorkspaceError("Agent must be a simple executable name, not a path or shell command")
    if conversation is not None and (not valid_conversation(conversation) or conversation["agent"] != agent):
        raise WorkspaceError("Invalid conversation metadata")
    pane = pane or os.environ.get("TMUX_PANE")
    if pane:
        best_effort(tmux.call, "set-option", "-p", "-t", pane, "@worktree_agent", agent)
        if conversation is None:
            best_effort(tmux.call, "set-option", "-p", "-u", "-t", pane, "@worktree_conversation")
        else:
            best_effort(tmux.call, "set-option", "-p", "-t", pane, "@worktree_conversation", json.dumps(conversation))
    if path is None and pane:
        try:
            path = tmux.value(pane, "#{@worktree_path}") or None
        except WorkspaceError:
            pass
    try:
        path, common = identify(path or cwd or os.getcwd())
    except WorkspaceError:
        if path is not None:
            raise
        return
    registry.remember(common, path, agent=agent, conversation=conversation)


def pane_conversation(tmux, pane):
    raw = best_effort(tmux.value, pane, "#{@worktree_conversation}") or "null"
    try:
        conversation = json.loads(raw)
    except ValueError:
        return None
    return conversation if valid_conversation(conversation) else None


def remember_conversation(tmux, registry, agent, cwd, session_id=None, session_file=None, path=None, pane=None):
    conversation = None
    if session_file:
        conversation = {"agent": agent, "session_id": session_id,
                        "session_file": canonical(session_file), "cwd": canonical(cwd)}
    remember_agent(tmux, registry, agent, path=path, pane=pane, conversation=conversation, cwd=cwd)


def record_hook(tmux, registry, agent, payload):
    if not isinstance(payload, dict):
        raise WorkspaceError("Expected a hook JSON object")
    if agent != "claude" or payload.get("agent_id") or payload.get("subagent_id"):
        return
    if payload.get("hook_event_name") not in ("SessionStart", "UserPromptSubmit", "Stop", "StopFailure"):
        return
    if not all(isinstance(payload.get(key), str) and payload[key] for key in ("cwd", "session_id", "transcript_path")):
        return
    cwd = payload["cwd"]
    pane = os.environ.get("TMUX_PANE")
    if pane and payload["hook_event_name"] != "SessionStart":
        previous = pane_conversation(tmux, pane)
        if (previous and previous["agent"] == agent and previous["session_id"] == payload["session_id"]
                and previous["session_file"] == canonical(payload["transcript_path"])):
            cwd = previous["cwd"]
    remember_conversation(tmux, registry, agent, cwd, payload["session_id"], payload["transcript_path"])


def resume_target(agent, conversation):
    if conversation is None:
        return None, []
    if not valid_conversation(conversation) or conversation["agent"] != agent:
        warn("Saved conversation metadata is invalid; starting a new conversation")
        return None, []
    try:
        cwd = conversation["cwd"]
        if not Path(cwd).is_dir():
            raise ValueError("its working directory no longer exists")
        with open(conversation["session_file"]) as stream:
            if agent == "pi":
                header = json.loads(stream.readline(65536))
                if (not isinstance(header, dict) or header.get("type") != "session"
                        or header.get("id") != conversation["session_id"]
                        or not isinstance(header.get("cwd"), str) or canonical(header["cwd"]) != cwd):
                    raise ValueError("its session header does not match")
        arguments = (["--session", conversation["session_file"]] if agent == "pi"
                     else ["--resume", conversation["session_id"]])
        return cwd, arguments
    except (OSError, ValueError) as error:
        warn(f"Cannot resume saved {agent} conversation ({error}); starting a new conversation")
        return None, []


def agent_shell(agent, registry, fresh=False):
    if agent and not valid_agent(agent):
        raise WorkspaceError("Invalid agent command name")
    require("zsh")
    workspace = os.getcwd()
    conversation = None
    if agent and not fresh:
        try:
            path, common = identify(workspace)
            record = preferences(registry.snapshot(), path, common)
            if record.get("agent") == agent:
                conversation = record.get("conversation")
        except WorkspaceError as error:
            warn(error)
    cwd, arguments = resume_target(agent, conversation)
    script = ('agent=$1; workspace=$2; resume_cwd=$3; shift 3; '
              'cd -- "$workspace" || exit 1; '
              'if [[ -z "$agent" ]]; then print -u2 "No agent recorded. Start an agent in this pane."; '
              'elif command -v -- "$agent" >/dev/null 2>&1; then '
              'if (( $# )); then '
              'if (cd -- "$resume_cwd" && "$agent" "$@"); then :; else result=$?; '
              'if (( result > 0 && result < 126 )); then '
              'print -u2 "Conversation resume failed; starting a new conversation."; "$agent" || true; fi; fi; '
              'else "$agent" || true; fi; '
              'else printf "Agent unavailable: %s. Start an agent in this pane.\\n" "$agent" >&2; fi; '
              'exec zsh -l')
    os.execvp("zsh", ["zsh", "-lic", script, "wta-agent", agent, workspace, cwd or workspace, *arguments])


def candidates(registry, tmux):
    data = registry.snapshot()
    sessions = tmux.sessions()
    rows = []
    seen = set()
    for common in data["repositories"]:
        if not isinstance(common, str) or not Path(common).is_absolute():
            warn("Ignoring an invalid repository registry entry")
            continue
        try:
            trees = git_worktrees(common)
        except WorkspaceError as error:
            warn(f"Skipping unavailable repository {common}: {error}")
            continue
        primary = next((item["worktree"] for item in trees if "worktree" in item and "bare" not in item), common)
        for tree in trees:
            if "worktree" not in tree or "bare" in tree:
                continue
            path = canonical(tree["worktree"])
            if path in seen:
                continue
            seen.add(path)
            if "prunable" in tree or not Path(path).is_dir():
                warn(f"Skipping missing or prunable worktree: {path}")
                continue
            record = preferences(data, path, common)
            session = tmux.matching(path, sessions)
            if session and session["name"] != record.get("session_name"):
                best_effort(registry.remember, common, path, session_name=session["name"])
            rows.append({"path": path, "repository": common, "repo": Path(primary).name,
                         "branch": tree.get("branch", "").removeprefix("refs/heads/") or "(detached)",
                         "session_name": session["name"] if session else record.get("session_name", ""),
                         "agent": record.get("agent"), "conversation": record.get("conversation"), "running": bool(session),
                         "updated_at": record.get("updated_at", 0)})
    return sorted(rows, key=lambda item: (not item["running"], -item["updated_at"], item["repo"], item["path"]))


def require(*commands):
    for command in commands:
        if not shutil.which(command):
            raise WorkspaceError(f"Requires {command} on PATH")


def create_workspace(tmux, registry, path, name, *, layout=False, move_pane=None, width=None, height=None, agent=None, fresh=False):
    if move_pane is not None and re.fullmatch(r"%[0-9]+", move_pane) is None:
        raise WorkspaceError("Moving an agent requires an exact tmux pane ID")
    require("tmux")
    if layout or move_pane:
        require("nvim", "lazygit")
    if layout and not move_pane:
        require("zsh")
    session_id = None
    try:
        args = ["new-session", "-d", "-P", "-F", "#{session_id} #{pane_id}" if layout or move_pane else "#{session_id}",
                "-s", name, "-c", path]
        if layout or move_pane:
            size = shutil.get_terminal_size((160, 50))
            args += ["-x", str(width or size.columns), "-y", str(height or size.lines), "nvim"]
        info = tmux.call(*args).split()
        session_id = info[0]
        tmux.call("set-option", "-t", session_id, "@worktree_path", path)
        if layout or move_pane:
            editor = info[1]
            git_pane = tmux.call("split-window", "-d", "-v", "-l", "40%", "-P", "-F", "#{pane_id}",
                                 "-t", editor, "-c", path, "lazygit")
            if move_pane:
                source_session, windows, panes = tmux.value(move_pane, "#{session_id} #{session_windows} #{window_panes}").split()
                if windows == "1" and panes == "1":
                    source_path = tmux.value(move_pane, "#{session_path}")
                    tmux.call("new-window", "-d", "-t", source_session + ":", "-c", source_path)
                tmux.call("join-pane", "-d", "-h", "-l", "60%", "-s", move_pane, "-t", git_pane)
                agent_pane = move_pane
            else:
                agent_pane = tmux.call("split-window", "-d", "-h", "-l", "60%", "-P", "-F", "#{pane_id}",
                                       "-t", git_pane, "-c", path, str(helper_path()), "agent-shell", agent or "",
                                       *(["--fresh"] if fresh else []))
            tmux.call("select-pane", "-t", agent_pane)
            if move_pane:
                moved_agent = best_effort(tmux.value, move_pane, "#{@worktree_agent}")
                if moved_agent and valid_agent(moved_agent):
                    conversation = pane_conversation(tmux, move_pane)
                    if conversation and conversation["agent"] != moved_agent:
                        conversation = None
                    best_effort(remember_agent, tmux, registry, moved_agent, path=path, pane=move_pane,
                                conversation=conversation)
        best_effort(remember_session, tmux, registry, session_id)
        return session_id
    except WorkspaceError as error:
        suffix = f" Workspace preserved: {name} ({session_id})." if session_id else ""
        raise WorkspaceError(str(error) + suffix) from error


def helper_path():
    return Path(__file__).resolve().parents[1] / "bin/wt-workspace"


def attach_worktree(path, agent, registry, tmux, fresh=False):
    path, common = identify(path)
    record = preferences(registry.snapshot(), path, common)
    if agent is not None:
        best_effort(registry.remember, common, path, agent=agent)
    else:
        agent = record.get("agent")
    sessions = tmux.sessions()
    session = tmux.matching(path, sessions)
    if session:
        session_id = session["id"]
        best_effort(remember_session, tmux, registry, session_id)
        best_effort(registry.remember, common, path, session_name=session["name"])
    else:
        name = record.get("session_name") or default_name(path, common)
        occupied = {item["name"] for item in sessions}
        if name in occupied:
            name += "-" + hashlib.sha256(os.fsencode(path)).hexdigest()[:8]
        if name in occupied:
            raise WorkspaceError(f"Tmux session name is occupied by another workspace: {name}")
        session_id = create_workspace(tmux, registry, path, name, layout=True, agent=agent, fresh=fresh)
    tmux.attach(session_id)


def display(value):
    return str(value).encode("unicode_escape").decode("ascii")


def pick(rows, query):
    require("fzf")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as snapshot:
        json.dump(rows, snapshot)
        snapshot.flush()
        preview = shlex.join([sys.executable, str(helper_path()), "preview", snapshot.name]) + " {1}"
        lines = [f"{index}\t{display(row['repo'])}\t{display(row['session_name'] or row['branch'])}\t"
                 f"{display(row['branch'])}\t{display(row['agent'] or '(unknown)')}\t"
                 f"{'running' if row['running'] else 'stopped'}\t{display(row['path'])}"
                 for index, row in enumerate(rows)]
        result = subprocess.run(["fzf", "--delimiter=\t", "--with-nth=2..", "--prompt=worktree> ",
                                 "--header=REPO / TASK / BRANCH / AGENT / SESSION / PATH", "--query", query or "",
                                 "--preview", preview, "--preview-window=right,55%,wrap"],
                                input="\n".join(lines) + "\n", capture_output=True, text=True)
        if result.returncode in (1, 130):
            return None
        if result.returncode:
            raise WorkspaceError(result.stderr.strip() or "fzf failed")
        try:
            index = int(result.stdout.split("\t", 1)[0])
            if index < 0:
                raise ValueError
            return rows[index]["path"]
        except (IndexError, ValueError) as error:
            raise WorkspaceError("Invalid worktree picker selection") from error


def wta_main(argv=None):
    parser = argparse.ArgumentParser(description="Attach to a registered worktree's tmux workspace.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--path")
    mode.add_argument("--register", metavar="REPO")
    mode.add_argument("--list", action="store_true", help="Print current worktrees as JSON")
    parser.add_argument("--agent", help="Remember a simple agent command name")
    parser.add_argument("--fresh", action="store_true", help="Start a new conversation when creating a workspace")
    parser.add_argument("query", nargs="?", help="Initial picker search")
    args = parser.parse_args(argv)
    if args.agent is not None and not valid_agent(args.agent):
        parser.error("--agent requires a simple executable name")
    direct = args.path is not None
    registering = args.register is not None
    if (direct and not args.path) or (registering and not args.register):
        parser.error("--path and --register require a nonempty path")
    if (args.query is not None and (direct or registering or args.list)) or ((args.agent or args.fresh) and (registering or args.list)):
        parser.error("query, --agent, and --fresh apply only to attachment")
    registry, tmux = Registry(), Tmux()
    try:
        require("git")
        if registering:
            common = repository(args.register)
            git_worktrees(common)
            registry.remember(common)
            print(f"Registered: {common}")
        elif direct:
            require("tmux")
            attach_worktree(args.path, args.agent, registry, tmux, fresh=args.fresh)
        else:
            rows = candidates(registry, tmux)
            if args.list:
                print(json.dumps(rows, indent=2))
            elif not rows:
                print("No worktrees registered. Use wta --register /path/to/repo.", file=sys.stderr)
            else:
                path = pick(rows, args.query)
                if path:
                    require("tmux")
                    attach_worktree(path, args.agent, registry, tmux, fresh=args.fresh)
    except WorkspaceError as error:
        parser.exit(1, f"wta: {error}\n")


def workspace_main(argv=None):
    parser = argparse.ArgumentParser(description="Shared worktree workspace operations.")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register")
    register.add_argument("path")
    remember = commands.add_parser("remember-agent")
    remember.add_argument("agent")
    remember.add_argument("--path")
    remember.add_argument("--pane")
    conversation = commands.add_parser("remember-conversation")
    conversation.add_argument("agent", choices=("pi", "claude"))
    conversation.add_argument("--cwd", required=True)
    conversation.add_argument("--session-id")
    conversation.add_argument("--session-file")
    conversation.add_argument("--path")
    conversation.add_argument("--pane")
    hook = commands.add_parser("record-hook")
    hook.add_argument("agent", choices=("claude",))
    session = commands.add_parser("remember-session")
    session.add_argument("--session", required=True)
    create = commands.add_parser("create")
    create.add_argument("--path", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--move-pane")
    create.add_argument("--width", type=int)
    create.add_argument("--height", type=int)
    shell = commands.add_parser("agent-shell")
    shell.add_argument("agent", nargs="?", default="")
    shell.add_argument("--fresh", action="store_true")
    preview = commands.add_parser("preview")
    preview.add_argument("snapshot")
    preview.add_argument("index", type=int)
    args = parser.parse_args(argv)
    registry, tmux = Registry(), Tmux()
    try:
        if args.command == "register":
            registry.remember(repository(args.path))
        elif args.command == "remember-agent":
            remember_agent(tmux, registry, args.agent, path=args.path, pane=args.pane)
        elif args.command == "remember-conversation":
            remember_conversation(tmux, registry, args.agent, args.cwd, args.session_id, args.session_file,
                                  path=args.path, pane=args.pane)
        elif args.command == "record-hook":
            record_hook(tmux, registry, args.agent, json.load(sys.stdin))
        elif args.command == "remember-session":
            remember_session(tmux, registry, args.session)
        elif args.command == "create":
            print(create_workspace(tmux, registry, args.path, args.name, move_pane=args.move_pane,
                                   width=args.width, height=args.height))
        elif args.command == "agent-shell":
            agent_shell(args.agent, registry, fresh=args.fresh)
        elif args.command == "preview":
            with open(args.snapshot) as stream:
                row = json.load(stream)[args.index]
            subprocess.run(["git", "-C", row["path"], "status", "--short", "--branch"])
    except (WorkspaceError, OSError, ValueError, IndexError) as error:
        parser.exit(1, f"wt-workspace: {error}\n")
