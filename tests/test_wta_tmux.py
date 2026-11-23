import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from test_wta import BIN, ROOT, RepositoryFixture, worktrees


TMUX = shutil.which("tmux")
ZSH = shutil.which("zsh")


@unittest.skipUnless(TMUX and ZSH, "tmux and zsh are required")
class WorkspaceTmuxTests(RepositoryFixture):
    def setUp(self):
        super().setUp()
        self.binaries = self.root / "bin"
        self.binaries.mkdir()
        (self.binaries / "python3").symlink_to(sys.executable)
        self.socket = str(self.root / "tmux.sock")
        self.home = self.root / "home"
        self.home.mkdir()
        self.launches = self.root / "launches"
        self.env.update({"HOME": str(self.home), "ZDOTDIR": str(self.home),
                         "PATH": str(self.binaries) + os.pathsep + str(BIN) + os.pathsep + os.environ["PATH"],
                         "WTA_LAUNCH_LOG": str(self.launches)})
        self.env["WTA_TEST_PATH"] = self.env["PATH"]
        wrapper = self.binaries / "tmux"
        wrapper.write_text(f"#!{sys.executable}\nimport os, subprocess, sys\n"
                           'if os.environ.get("WTA_SPLIT_FAIL") and sys.argv[1] == "split-window":\n'
                           '    sys.exit(1)\n'
                           f"sys.exit(subprocess.call([{TMUX!r}, '-S', {self.socket!r}, '-f', '/dev/null', *sys.argv[1:]]))\n")
        wrapper.chmod(0o755)
        for name in ("nvim", "lazygit"):
            path = self.binaries / name
            path.write_text("#!/bin/sh\nexec /bin/sleep 600\n")
            path.chmod(0o755)
        (self.home / ".zshenv").write_text('unsetopt GLOBAL_RCS\nexport PATH="$WTA_TEST_PATH"\nexport HISTFILE=/dev/null\n')
        (self.home / ".zshrc").write_text('pi() { wt-workspace remember-agent pi; print pi >> "$WTA_LAUNCH_LOG"; sleep 600; }\n')
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.tmux = worktrees.Tmux()
        self.tmux.call("new-session", "-d", "-s", "seed", "-c", str(self.repo), "-x", "160", "-y", "60", "sleep 600")
        self.addCleanup(self.stop_server)
        self.tmux.call("set-option", "-g", "default-shell", ZSH)

    def stop_server(self):
        subprocess.run([TMUX, "-S", self.socket, "kill-server"], capture_output=True, timeout=10)

    def wait_for(self, condition):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.02)
        self.fail("Timed out waiting for tmux child process")

    def panes(self, session):
        raw = self.tmux.call("list-panes", "-s", "-t", session, "-F",
                             "#{pane_id}\t#{pane_left}\t#{pane_top}\t#{pane_width}\t#{pane_height}\t#{pane_start_path}\t#{pane_active}\t#{pane_pid}")
        return [line.split("\t") for line in raw.splitlines()]

    def attach(self, path=None, agent=None, fresh=False):
        with patch.object(worktrees.Tmux, "attach") as attach:
            worktrees.attach_worktree(str(path or self.tree), agent, self.registry, self.tmux, fresh=fresh)
        return attach.call_args.args[0]

    def test_recreates_layout_launches_shell_function_and_reuses_session(self):
        session = self.attach(agent="pi")
        self.wait_for(self.launches.exists)
        panes = self.panes(session)
        self.assertEqual(len(panes), 3)
        editor, bottom_left, agent = sorted(panes, key=lambda pane: (int(pane[2]), int(pane[1])))
        self.assertEqual(editor[1:3], ["0", "0"])
        self.assertEqual(editor[3], "160")
        self.assertGreater(int(editor[4]), int(agent[4]))
        self.assertEqual(bottom_left[2], agent[2])
        self.assertGreater(int(agent[3]), int(bottom_left[3]))
        self.assertEqual([pane[5] for pane in panes], [str(self.tree)] * 3)
        self.assertEqual(agent[6], "1")
        before = [(pane[0], pane[7]) for pane in panes]
        self.assertEqual(self.attach(agent="claude"), session)
        self.assertEqual([(pane[0], pane[7]) for pane in self.panes(session)], before)
        self.assertEqual(self.launches.read_text(), "pi\n")
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["agent"], "claude")

    def test_missing_agent_and_unknown_agent_leave_usable_shells(self):
        for agent in (None, "wta-agent-not-installed"):
            with self.subTest(agent=agent):
                session = self.attach(agent=agent)
                pane = next(item for item in self.panes(session) if item[6] == "1")[0]
                marker = self.root / "shell-ready"
                self.tmux.call("send-keys", "-t", pane, "printf ready > " + shlex.quote(str(marker)), "Enter")
                self.wait_for(marker.exists)
                self.assertEqual(marker.read_text(), "ready")
                marker.unlink()
                self.tmux.call("kill-session", "-t", session)

    def test_agent_exit_leaves_shell(self):
        (self.home / ".zshrc").write_text('pi() { print pi >> "$WTA_LAUNCH_LOG"; return 9; }\n')
        session = self.attach(agent="pi")
        self.wait_for(self.launches.exists)
        pane = next(item for item in self.panes(session) if item[6] == "1")[0]
        marker = self.root / "after-agent"
        self.tmux.call("send-keys", "-t", pane, "printf ready > " + shlex.quote(str(marker)), "Enter")
        self.wait_for(marker.exists)
        self.assertEqual(marker.read_text(), "ready")

    def test_rename_hook_persists_name_for_kill_and_recreation(self):
        text = (ROOT / "tmux/.config/tmux/tmux.conf").read_text()
        hook = text[text.index("set-hook -g 'session-renamed[42]'"):].split("\n}\n", 1)[0] + "\n}\n"
        hook = hook.replace("$HOME/.local/bin/wt-workspace", str(BIN / "wt-workspace"))
        config = self.root / "hooks.conf"
        config.write_text(hook)
        self.tmux.call("source-file", str(config))
        self.tmux.call("source-file", str(config))
        session = self.attach()
        self.tmux.call("rename-session", "-t", session, "SERVEBX-100-task")
        self.wait_for(lambda: self.registry.read()["worktrees"].get(str(self.tree), {}).get("session_name") == "SERVEBX-100-task")
        self.tmux.call("kill-session", "-t", session)
        recreated = self.attach()
        self.assertEqual(self.tmux.value(recreated, "#{session_name}"), "SERVEBX-100-task")
        self.assertEqual(len(self.panes(recreated)), 3)
        self.assertEqual(self.tmux.call("show-hooks", "-g").count("session-renamed[42]"), 1)

    def test_legacy_session_path_is_reused_without_tag_or_layout_changes(self):
        session = self.tmux.call("new-session", "-d", "-P", "-F", "#{session_id}", "-s", "legacy", "-c", str(self.tree), "sleep 600")
        self.assertEqual(self.attach(), session)
        self.assertEqual(len(self.panes(session)), 1)
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["session_name"], "legacy")

    def test_moved_agent_is_recorded_without_using_its_original_cwd(self):
        source_pane = self.panes("=seed")[0][0]
        source_pid = self.tmux.value(source_pane, "#{pane_pid}")
        self.tmux.call("set-option", "-p", "-t", source_pane, "@worktree_agent", "claude")
        session = worktrees.create_workspace(self.tmux, self.registry, str(self.tree), "moved", move_pane=source_pane, width=160, height=60)
        self.assertEqual(self.tmux.value(source_pane, "#{pane_pid}"), source_pid)
        self.assertEqual(self.tmux.value(source_pane, "#{pane_current_path}"), str(self.repo))
        self.assertEqual(self.tmux.value(source_pane, "#{session_id}"), session)
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["agent"], "claude")
        self.assertEqual(len(self.panes("=seed")), 1)

    def install_logging_agent(self, name="pi", resume_exit=None):
        binary = self.binaries / "record-agent"
        binary.write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                          'with open(os.environ["WTA_LAUNCH_LOG"], "a") as stream:\n'
                          '    stream.write(json.dumps({"cwd": os.getcwd(), "arguments": sys.argv[1:]}) + "\\n")\n'
                          + (f"if sys.argv[1:]: sys.exit({resume_exit})\n" if resume_exit is not None else "")
                          + 'os.execl("/bin/sleep", "sleep", "600")\n')
        binary.chmod(0o755)
        (self.home / ".zshrc").write_text(f'{name}() {{ command {shlex.quote(str(binary))} "$@"; }}\n')

    def saved_conversation(self, agent="pi"):
        session_id = "pi-session" if agent == "pi" else "c167920c-e037-43c0-b1bd-33a5eb65a287"
        session_file = self.root / f"{session_id}.jsonl"
        session_file.write_text(json.dumps({"type": "session", "id": session_id, "cwd": str(self.repo)}) + "\n")
        worktrees.remember_conversation(self.tmux, self.registry, agent, str(self.repo), session_id,
                                       str(session_file), path=str(self.tree))
        return self.registry.read()["worktrees"][str(self.tree)]["conversation"]

    def launch_records(self):
        return [json.loads(line) for line in self.launches.read_text().splitlines()] if self.launches.exists() else []

    def test_exact_pi_conversation_resumes_after_killing_the_workspace(self):
        self.install_logging_agent()
        conversation = self.saved_conversation()
        session = self.attach()
        self.wait_for(lambda: len(self.launch_records()) == 1)
        self.assertEqual(self.launch_records()[0], {"cwd": str(self.repo), "arguments": ["--session", conversation["session_file"]]})
        self.assertEqual({pane[5] for pane in self.panes(session)}, {str(self.tree)})
        self.tmux.call("kill-session", "-t", session)
        self.attach()
        self.wait_for(lambda: len(self.launch_records()) == 2)
        self.assertEqual(self.launch_records()[1], self.launch_records()[0])

    def test_claude_resumes_by_uuid_in_its_original_directory(self):
        self.install_logging_agent("claude")
        conversation = self.saved_conversation("claude")
        self.attach()
        self.wait_for(self.launches.exists)
        self.assertEqual(self.launch_records()[0], {"cwd": str(self.repo), "arguments": ["--resume", conversation["session_id"]]})

    def test_stale_metadata_and_fresh_flag_start_normally_in_the_worktree(self):
        self.install_logging_agent()
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                conversation = self.saved_conversation()
                if not fresh:
                    Path(conversation["session_file"]).unlink()
                count = len(self.launch_records())
                session = self.attach(fresh=fresh)
                self.wait_for(lambda: len(self.launch_records()) == count + 1)
                self.assertEqual(self.launch_records()[-1], {"cwd": str(self.tree), "arguments": []})
                self.tmux.call("kill-session", "-t", session)

    def test_failed_native_resume_falls_back_once_without_reusing_flags(self):
        self.install_logging_agent(resume_exit=1)
        rc = self.home / ".zshrc"
        rc.write_text("setopt errexit\n" + rc.read_text())
        conversation = self.saved_conversation()
        self.attach()
        self.wait_for(lambda: len(self.launch_records()) == 2)
        self.assertEqual(self.launch_records(), [
            {"cwd": str(self.repo), "arguments": ["--session", conversation["session_file"]]},
            {"cwd": str(self.tree), "arguments": []},
        ])

    def test_interrupted_resume_does_not_start_a_second_conversation(self):
        self.install_logging_agent(resume_exit=130)
        self.saved_conversation()
        session = self.attach()
        self.wait_for(self.launches.exists)
        pane = next(item for item in self.panes(session) if item[6] == "1")[0]
        marker = self.root / "shell-after-interrupt"
        self.tmux.call("send-keys", "-t", pane, "printf ready > " + shlex.quote(str(marker)), "Enter")
        self.wait_for(marker.exists)
        self.assertEqual(len(self.launch_records()), 1)

    def test_moving_a_pane_transfers_its_conversation_reference(self):
        self.install_logging_agent()
        conversation = self.saved_conversation()
        pane = self.panes("=seed")[0][0]
        self.tmux.call("set-option", "-p", "-t", pane, "@worktree_agent", "pi")
        self.tmux.call("set-option", "-p", "-t", pane, "@worktree_conversation", json.dumps(conversation))
        session = worktrees.create_workspace(self.tmux, self.registry, str(self.tree), "moved-conversation",
                                            move_pane=pane, width=160, height=60)
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["conversation"], conversation)
        self.tmux.call("kill-session", "-t", session)
        self.attach()
        self.wait_for(self.launches.exists)
        self.assertEqual(self.launch_records()[0]["arguments"], ["--session", conversation["session_file"]])

    def test_claude_status_hook_captures_the_conversation_without_extra_output(self):
        pane = self.panes("=seed")[0][0]
        session = self.tmux.value(pane, "#{session_id}")
        self.tmux.call("set-option", "-t", session, "@worktree_path", str(self.tree))
        payload = {"hook_event_name": "SessionStart", "session_id": "c167920c-e037-43c0-b1bd-33a5eb65a287",
                   "transcript_path": str(self.root / "claude.jsonl"), "cwd": str(self.repo)}
        result = subprocess.run([str(BIN / "agent-status"), "set", "claude", "idle"],
                                input=json.dumps(payload), capture_output=True, text=True,
                                env={**self.env, "TMUX_PANE": pane}, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.registry.read()["worktrees"][str(self.tree)]["conversation"]["session_id"], payload["session_id"])

    def test_partial_creation_failure_is_reported_without_attaching(self):
        with patch.dict(os.environ, {"WTA_SPLIT_FAIL": "1"}), patch.object(worktrees.Tmux, "attach") as attach:
            with self.assertRaisesRegex(worktrees.WorkspaceError, "Workspace preserved"):
                worktrees.attach_worktree(str(self.tree), None, self.registry, self.tmux)
        attach.assert_not_called()
        self.assertEqual(len(self.tmux.sessions()), 2)


if __name__ == "__main__":
    unittest.main()
