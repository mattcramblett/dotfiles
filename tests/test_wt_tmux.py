import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_wt import STUB, WT


TMUX = shutil.which("tmux")
CONFIG = WT.parents[3] / "tmux/.config/tmux/tmux.conf"


@unittest.skipUnless(TMUX, "tmux is not installed")
class WorktreeLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wt tmux ", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.worktree = self.root / "repo-feature-login"
        binaries = self.root / "bin"
        binaries.mkdir()
        self.socket = str(self.root / "tmux.sock")
        self.env = {
            **os.environ,
            "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "XDG_STATE_HOME": str(self.root / "state"),
            "WT_TEST_LOG": str(self.root / "calls.jsonl"),
            "WT_TEST_REPO": str(self.repo),
            "WT_TEST_REFS": json.dumps(["refs/heads/feature/login"]),
        }
        self.env.pop("TMUX", None)
        self.env.pop("TMUX_PANE", None)
        git = binaries / "git"
        git.write_text(f"#!{sys.executable}\n" + STUB)
        git.chmod(0o755)
        tmux = binaries / "tmux"
        tmux.write_text(
            f"#!{sys.executable}\n"
            "import os, subprocess, sys\n"
            "if os.environ.get('WT_TEST_LAYOUT_FAIL') and sys.argv[1] == 'split-window':\n"
            "    sys.exit(1)\n"
            f"sys.exit(subprocess.call([{TMUX!r}, '-S', {self.socket!r}, '-f', '/dev/null', *sys.argv[1:]]))\n"
        )
        tmux.chmod(0o755)
        for name in ("nvim", "lazygit"):
            binary = binaries / name
            binary.write_text("#!/bin/sh\nexec /bin/sleep 600\n")
            binary.chmod(0o755)

        self.agent_pane = self.tmux(
            "new-session", "-d", "-P", "-F", "#{pane_id}", "-s", "main",
            "-c", str(self.repo), "-x", "160", "-y", "60", "sleep 600",
        )
        self.addCleanup(self.stop_server)
        self.tmux("set-option", "-g", "default-shell", "/bin/sh")
        self.tmux("set-option", "-g", "base-index", "1")
        self.tmux("set-option", "-g", "pane-base-index", "1")
        self.tmux("set-option", "-g", "renumber-windows", "on")
        self.agent_pid = self.tmux("display-message", "-p", "-t", self.agent_pane, "#{pane_pid}")
        self.source_session = self.tmux("display-message", "-p", "-t", self.agent_pane, "#{session_id}")

        config = self.root / "bindings.conf"
        config.write_text("\n".join(
            line for line in CONFIG.read_text().splitlines()
            if line.startswith(("bind c ", "bind '\"' ", "bind % "))
        ) + "\n")
        self.tmux("source-file", str(config))

    def tmux(self, *args):
        result = subprocess.run(
            [TMUX, "-S", self.socket, "-f", "/dev/null", *args],
            cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def stop_server(self):
        subprocess.run(
            [TMUX, "-S", self.socket, "kill-server"],
            capture_output=True, timeout=10,
        )

    def move_agent(self, **env):
        return subprocess.run(
            ["/bin/bash", str(WT), "--background", "--move-pane", self.agent_pane, "feature/login"],
            cwd=self.repo,
            env={**self.env, "TMUX": f"{self.socket},0,0", "TMUX_PANE": self.agent_pane, **env},
            capture_output=True, text=True, timeout=30,
        )

    def binding(self, key):
        for line in self.tmux("list-keys", "-T", "prefix").splitlines():
            args = shlex.split(line)
            key_index = args.index("prefix") + 1
            if args[key_index] == key:
                return args[key_index + 1:]
        self.fail(f"Missing prefix binding: {key}")

    def panes(self, session):
        output = self.tmux(
            "list-panes", "-s", "-t", session, "-F",
            "#{pane_id}\t#{pane_pid}\t#{pane_left}\t#{pane_top}\t#{pane_width}\t#{pane_height}\t#{pane_start_command}\t#{pane_start_path}",
        )
        return [line.split("\t") for line in output.splitlines()]

    def assert_agent_preserved(self):
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", self.agent_pane, "#{pane_pid}"),
            self.agent_pid,
        )
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", self.agent_pane, "#{pane_current_path}"),
            str(self.repo),
        )

    def test_layout_preserves_process_and_other_main_panes(self):
        sibling = self.tmux(
            "split-window", "-d", "-h", "-P", "-F", "#{pane_id}",
            "-t", self.agent_pane, "-c", str(self.repo), "sleep 600",
        )
        sibling_pid = self.tmux("display-message", "-p", "-t", sibling, "#{pane_pid}")
        result = self.move_agent()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Tmux session: repo-feature-login", result.stdout)
        self.assert_agent_preserved()

        panes = self.panes("=repo-feature-login")
        self.assertEqual(len(panes), 3)
        agent = next(p for p in panes if p[0] == self.agent_pane)
        editor = next(p for p in panes if p[6] == "nvim")
        lazygit = next(p for p in panes if p[6] == "lazygit")
        self.assertEqual(editor[2:4], ["0", "0"])
        self.assertEqual(editor[4], "160")
        self.assertGreater(int(editor[5]), int(agent[5]))
        self.assertEqual(lazygit[2], "0")
        self.assertEqual(lazygit[3], agent[3])
        self.assertEqual(lazygit[5], agent[5])
        self.assertGreater(int(agent[2]), 0)
        self.assertGreater(int(agent[4]), int(lazygit[4]))
        self.assertEqual(editor[7], str(self.worktree))
        self.assertEqual(lazygit[7], str(self.worktree))
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", self.agent_pane, "#{session_path}"),
            str(self.worktree),
        )
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", self.agent_pane, "#{pane_active}"), "1",
        )
        main_panes = self.panes("=main")
        self.assertEqual([(p[0], p[1]) for p in main_panes], [(sibling, sibling_pid)])

    def test_moving_last_pane_leaves_main_session_alive(self):
        result = self.move_agent()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_agent_preserved()
        self.assertEqual(len(self.panes("=repo-feature-login")), 3)
        self.assertEqual(len(self.panes("=main")), 1)
        self.assertNotEqual(self.panes("=main")[0][0], self.agent_pane)
        self.assertEqual(self.panes("=main")[0][7], str(self.repo))
        self.assertEqual(
            self.tmux("display-message", "-p", "-t", "main:", "#{session_id}"), self.source_session,
        )

    def test_new_window_and_split_bindings_use_worktree_not_agent_cwd(self):
        result = self.move_agent()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_agent_preserved()
        session = self.tmux("display-message", "-p", "-t", self.agent_pane, "#{session_id}")
        for key, command in (("c", "new-window"), ('"', "split-window"), ("%", "split-window")):
            with self.subTest(key=key):
                args = self.binding(key)
                self.assertEqual(args[0], command)
                target = session + ":" if command == "new-window" else self.agent_pane
                path = self.tmux(
                    *args, "-d", "-t", target, "-P", "-F", "#{pane_start_path}", "sleep 600",
                )
                self.assertEqual(path, str(self.worktree))

    def test_bindings_preserve_normal_session_paths(self):
        for key, command in (("c", "new-window"), ('"', "split-window"), ("%", "split-window")):
            with self.subTest(key=key):
                args = self.binding(key)
                self.assertEqual(args[0], command)
                target = self.source_session + ":" if command == "new-window" else self.agent_pane
                path = self.tmux(
                    *args, "-d", "-t", target, "-P", "-F", "#{pane_start_path}", "sleep 600",
                )
                self.assertEqual(path, str(self.repo))

    def test_layout_failure_leaves_agent_in_main_session(self):
        result = self.move_agent(WT_TEST_LAYOUT_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Tmux session:", result.stdout)
        self.assert_agent_preserved()
        self.assertEqual(self.panes("=main")[0][0], self.agent_pane)
        self.assertTrue(self.worktree.is_dir())


if __name__ == "__main__":
    unittest.main()
