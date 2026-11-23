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
        (self.home / ".zshenv").write_text('export PATH="$WTA_TEST_PATH"\n')
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

    def attach(self, path=None, agent=None):
        with patch.object(worktrees.Tmux, "attach") as attach:
            worktrees.attach_worktree(str(path or self.tree), agent, self.registry, self.tmux)
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

    def test_partial_creation_failure_is_reported_without_attaching(self):
        with patch.dict(os.environ, {"WTA_SPLIT_FAIL": "1"}), patch.object(worktrees.Tmux, "attach") as attach:
            with self.assertRaisesRegex(worktrees.WorkspaceError, "Workspace preserved"):
                worktrees.attach_worktree(str(self.tree), None, self.registry, self.tmux)
        attach.assert_not_called()
        self.assertEqual(len(self.tmux.sessions()), 2)


if __name__ == "__main__":
    unittest.main()
