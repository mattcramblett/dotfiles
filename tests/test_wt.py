import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


WT = Path(__file__).resolve().parents[1] / "bin/.local/bin/wt"
STUB = r'''
import json
import os
from pathlib import Path
import sys

command = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["WT_TEST_LOG"], "a") as log:
    log.write(json.dumps([command, args, os.getcwd()]) + "\n")

if command == "git":
    directory = args[1] if args[0] == "-C" else os.getcwd()
    if args[0] == "-C":
        args = args[2:]
    if args[0] == "rev-parse":
        print(directory if args[-1] == "--show-toplevel" else os.environ["WT_TEST_REPO"] + "/.git")
    elif args[0] == "ls-files":
        for path in sorted(Path(directory).rglob("*")):
            if path.is_file():
                print(str(path.relative_to(directory)) + "\0", end="")
    elif args[:2] == ["worktree", "list"]:
        repo = Path(os.environ["WT_TEST_REPO"])
        for path in [repo, *repo.parent.glob(repo.name + "-*")]:
            print(f"worktree {path}\0branch refs/heads/feature/login\0\0", end="")
    elif args[0] == "config":
        print(os.environ.get("WT_TEST_PREFIX", "mattcramblett/"))
    elif args[0] == "show-ref":
        sys.exit(0 if args[-1] in json.loads(os.environ["WT_TEST_REFS"]) else 1)
    elif args[:3] == ["remote", "get-url", "origin"]:
        print("git@example.com:repo.git")
    elif args[:2] == ["worktree", "add"]:
        if os.environ.get("WT_TEST_ADD_FAIL"):
            sys.exit(1)
        path = Path(args[args.index("--track") + 1] if "--track" in args else args[-2])
        path.mkdir()
        if os.environ.get("WT_TEST_TOOL_VERSIONS"):
            (path / ".tool-versions").touch()
        for name, contents in json.loads(os.environ.get("WT_TEST_FILES", "{}")).items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents)
elif command == "tmux":
    if args[0] == "has-session":
        sys.exit(0 if os.environ.get("WT_TEST_SESSION_EXISTS") else 1)
    elif args[0] == "new-session":
        if os.environ.get("WT_TEST_SESSION_FAIL"):
            sys.exit(1)
        print("$42 %21" if args[args.index("-F") + 1] == "#{session_id} #{pane_id}" else "$42")
    elif args[0] == "display-message":
        if os.environ.get("WT_TEST_PANE_MISSING"):
            sys.exit(1)
        calls = [json.loads(line) for line in Path(os.environ["WT_TEST_LOG"]).read_text().splitlines()]
        paths = [call[1][-1] for call in calls if call[0] == "tmux" and call[1][0] == "set-option" and "@worktree_path" in call[1]]
        names = [call[1][call[1].index("-s") + 1] for call in calls if call[0] == "tmux" and call[1][0] == "new-session"]
        print({
            "#{@worktree_path}": paths[-1] if paths else "",
            "#{session_name}": names[-1] if names else "",
            "#{@worktree_agent}": os.environ.get("WT_TEST_AGENT", ""),
            "#{@worktree_conversation}": os.environ.get("WT_TEST_CONVERSATION", ""),
            "#{pane_id} #{window_width} #{window_height}": "%7 160 60",
            "#{session_id} #{session_windows} #{window_panes}":
                os.environ.get("WT_TEST_SOURCE_INFO", "$1 1 2"),
            "#{session_path}": os.environ["WT_TEST_REPO"],
        }[args[-1]])
    elif args[0] == "split-window":
        if os.environ.get("WT_TEST_SPLIT_FAIL"):
            sys.exit(1)
        print("%22")
    elif args[0] == "join-pane":
        if os.environ.get("WT_TEST_JOIN_FAIL"):
            sys.exit(1)
    elif args[0] not in ("set-option", "select-pane", "new-window"):
        assert args == ["switch-client", "-t", "$42"], args
elif command == "asdf":
    assert args == ["install"], args
    sys.exit(int(os.environ.get("WT_TEST_ASDF_EXIT", "0")))
elif command == "npm":
    if args == ["--version"]:
        print("10.0.0")
    else:
        assert args == ["ci"], args
        sys.exit(int(os.environ.get("WT_TEST_NPM_EXIT", "0")))
'''


class WorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wt tests ")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.repo = root / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.worktree = root / "repo-feature-login"
        self.log = root / "calls.jsonl"
        binaries = root / "bin"
        binaries.mkdir()
        for name in ("git", "tmux", "asdf", "nvim", "lazygit", "npm"):
            stub = binaries / name
            stub.write_text(f"#!{sys.executable}\n" + STUB)
            stub.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "TMUX": "test-session",
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "WT_TEST_LOG": str(self.log),
            "WT_TEST_REPO": str(self.repo),
            "WT_TEST_REFS": json.dumps(["refs/remotes/origin/main"]),
        }

    def run_wt(self, *args, **env):
        return subprocess.run(
            ["/bin/bash", str(WT), *(args or ("feature/login",))],
            cwd=self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
        )

    def calls(self, command=None):
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        metadata_queries = ("#{@worktree_path}", "#{session_name}", "#{@worktree_agent}", "#{@worktree_conversation}")
        return [call for call in calls if (command is None or call[0] == command)
                and not (call[0] == "tmux" and call[1][0] == "display-message"
                         and call[1][-1] in metadata_queries)]

    def test_installs_in_worktree_before_creating_and_switching_session(self):
        result = self.run_wt(WT_TEST_TOOL_VERSIONS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("asdf"), [["asdf", ["install"], str(self.worktree)]])
        self.assertEqual(
            [call[1] for call in self.calls("tmux")],
            [
                ["has-session", "-t", "=repo-feature-login"],
                ["new-session", "-d", "-P", "-F", "#{session_id}",
                 "-s", "repo-feature-login", "-c", str(self.worktree)],
                ["set-option", "-t", "$42", "@worktree_path", str(self.worktree)],
                ["switch-client", "-t", "$42"],
            ],
        )
        commands = [call[0] for call in self.calls()]
        self.assertLess(commands.index("asdf"), len(commands) - 2)

    def test_dependency_install_finishes_before_pane_move(self):
        result = self.run_wt(
            "--background", "--no-reuse", "--move-pane", "%7", "feature/login",
            WT_TEST_FILES=json.dumps({"package.json": "{}", "package-lock.json": "{}"}),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        install = next(i for i, call in enumerate(calls) if call[:2] == ["npm", ["ci"]])
        session = next(i for i, call in enumerate(calls) if call[0] == "tmux" and call[1][0] == "new-session")
        self.assertLess(install, session)
        self.assertEqual(calls[install][2], str(self.worktree))

    def test_dependency_failure_preserves_worktree_and_agent(self):
        result = self.run_wt(
            "--background", "--move-pane", "%7", "feature/login",
            WT_TEST_FILES=json.dumps({"package.json": "{}", "package-lock.json": "{}"}),
            WT_TEST_NPM_EXIT="9",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.worktree / "package.json").is_file())
        self.assertIn("Retry with: wt-setup --path", result.stderr)
        self.assertFalse(any(call[1][0] in ("new-session", "join-pane") for call in self.calls("tmux")))
        self.assertNotIn("Tmux session:", result.stdout)

    def test_skips_asdf_without_tool_versions(self):
        result = self.run_wt()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("asdf"), [])
        self.assertEqual(self.calls("tmux")[-1][1], ["switch-client", "-t", "$42"])

    def test_install_failure_preserves_worktree_without_creating_session(self):
        result = self.run_wt(WT_TEST_TOOL_VERSIONS="1", WT_TEST_ASDF_EXIT="7")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("asdf install failed", result.stderr)
        self.assertIn(str(self.worktree), result.stderr)
        self.assertTrue(self.worktree.is_dir())
        self.assertEqual(len(self.calls("tmux")), 1)
        registry = Path(self.env["XDG_STATE_HOME"]) / "worktrees/registry.json"
        self.assertEqual(json.loads(registry.read_text())["repositories"], [str(self.repo / ".git")])

    def test_registry_failure_does_not_interrupt_worktree_creation(self):
        blocked = self.repo.parent / "blocked-state"
        blocked.write_text("preserve")
        result = self.run_wt(XDG_STATE_HOME=str(blocked))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.worktree.is_dir())
        self.assertEqual(self.calls("tmux")[-1][1], ["switch-client", "-t", "$42"])
        self.assertIn("Cannot update", result.stderr)
        self.assertEqual(blocked.read_text(), "preserve")

    def test_existing_session_is_rejected_before_creating_worktree(self):
        result = self.run_wt(WT_TEST_SESSION_EXISTS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Tmux session already exists", result.stderr)
        self.assertFalse(self.worktree.exists())
        self.assertFalse(any(call[1][:2] == ["worktree", "add"] for call in self.calls("git")))

    def test_session_name_normalizes_dots_and_keeps_directory_name(self):
        result = self.run_wt("mattcramblett/feature.v2/login")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = next(call[1] for call in self.calls("tmux") if call[1][0] == "new-session")
        self.assertEqual(args[args.index("-s") + 1], "repo-feature_v2-login")
        self.assertEqual(args[args.index("-c") + 1], str(self.repo.parent / "repo-feature.v2-login"))

    def test_preserves_local_remote_and_default_branch_selection(self):
        for refs, expected in [
            (["refs/heads/feature/login"], [str(self.worktree), "feature/login"]),
            (["refs/remotes/origin/feature/login"],
             ["-b", "feature/login", "--track", str(self.worktree), "origin/feature/login"]),
            (["refs/remotes/origin/master"],
             ["-b", "feature/login", str(self.worktree), "origin/master"]),
        ]:
            with self.subTest(refs=refs):
                result = self.run_wt(WT_TEST_REFS=json.dumps(refs))
                self.assertEqual(result.returncode, 0, result.stderr)
                args = [call[1][2:] for call in self.calls("git") if call[1][:2] == ["worktree", "add"]]
                self.assertEqual(args[-1], expected)
                self.worktree.rmdir()

    def test_worktree_failure_stops_before_install_or_session_creation(self):
        result = self.run_wt(WT_TEST_ADD_FAIL="1", WT_TEST_TOOL_VERSIONS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls("asdf"), [])
        self.assertEqual(len(self.calls("tmux")), 1)

    def test_session_creation_failure_does_not_switch_client(self):
        result = self.run_wt(WT_TEST_SESSION_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.worktree.is_dir())
        self.assertEqual(self.calls("tmux")[-1][1][0], "new-session")

    def test_background_does_not_switch_client_inside_tmux(self):
        result = self.run_wt("--background", "feature/login", WT_TEST_TOOL_VERSIONS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("asdf"), [["asdf", ["install"], str(self.worktree)]])
        self.assertEqual(self.calls("tmux")[-1][1][0], "set-option")
        self.assertEqual(len(self.calls("tmux")), 3)
        commands = [call[0] for call in self.calls()]
        self.assertLess(commands.index("asdf"), len(commands) - 2)
        self.assertIn(f"Worktree: {self.worktree}", result.stdout)
        self.assertIn("Tmux session: repo-feature-login", result.stdout)

    def test_background_works_without_tmux_environment(self):
        result = self.run_wt("--background", "feature/login", TMUX="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.worktree.is_dir())
        self.assertEqual(self.calls("tmux")[-1][1][0], "set-option")
        self.assertEqual(len(self.calls("tmux")), 3)

    def test_background_install_failure_does_not_report_success(self):
        result = self.run_wt(
            "--background", "feature/login", TMUX="",
            WT_TEST_TOOL_VERSIONS="1", WT_TEST_ASDF_EXIT="7",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("asdf install failed", result.stderr)
        self.assertTrue(self.worktree.is_dir())
        self.assertEqual(len(self.calls("tmux")), 1)
        self.assertNotIn("Tmux session:", result.stdout)

    def test_background_session_failure_does_not_report_success(self):
        result = self.run_wt("--background", "feature/login", WT_TEST_SESSION_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.worktree.is_dir())
        self.assertNotIn("Tmux session:", result.stdout)

    def test_background_requires_exactly_one_branch(self):
        for args in [("--background",), ("--background", "feature/login", "extra")]:
            with self.subTest(args=args):
                result = self.run_wt(*args, TMUX="")
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage: wt [--background] [--move-pane <pane-id>] [--no-reuse] <branch-name>", result.stderr)
                self.assertFalse(self.log.exists())

    def test_background_help_does_not_require_tmux(self):
        result = self.run_wt("--background", "--help", TMUX="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--background leaves the session detached", result.stdout)
        self.assertFalse(self.log.exists())

    def test_move_pane_builds_layout_before_moving_exact_pane(self):
        result = self.run_wt("--background", "--move-pane", "%7", "feature/login",
                             WT_TEST_TOOL_VERSIONS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [call[1] for call in self.calls("tmux")]
        self.assertEqual(calls, [
            ["display-message", "-p", "-t", "%7", "#{pane_id} #{window_width} #{window_height}"],
            ["has-session", "-t", "=repo-feature-login"],
            ["new-session", "-d", "-P", "-F", "#{session_id} #{pane_id}",
             "-s", "repo-feature-login", "-c", str(self.worktree), "-x", "160", "-y", "60", "nvim"],
            ["set-option", "-t", "$42", "@worktree_path", str(self.worktree)],
            ["split-window", "-d", "-v", "-l", "40%", "-P", "-F", "#{pane_id}",
             "-t", "%21", "-c", str(self.worktree), "lazygit"],
            ["display-message", "-p", "-t", "%7", "#{session_id} #{session_windows} #{window_panes}"],
            ["join-pane", "-d", "-h", "-l", "60%", "-s", "%7", "-t", "%22"],
            ["select-pane", "-t", "%7"],
        ])
        commands = [call[0] for call in self.calls()]
        self.assertLess(commands.index("asdf"), len(commands) - 6)
        self.assertIn("Tmux session: repo-feature-login", result.stdout)

    def test_move_pane_remembers_the_source_agent(self):
        result = self.run_wt("--background", "--move-pane", "%7", "feature/login", WT_TEST_AGENT="claude")
        self.assertEqual(result.returncode, 0, result.stderr)
        registry = Path(self.env["XDG_STATE_HOME"]) / "worktrees/registry.json"
        self.assertEqual(json.loads(registry.read_text())["worktrees"][str(self.worktree)]["agent"], "claude")

    def test_move_pane_preserves_other_source_windows_without_replacement(self):
        result = self.run_wt("--background", "--move-pane", "%7", "feature/login",
                             WT_TEST_SOURCE_INFO="$1 2 1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("new-window", [call[1][0] for call in self.calls("tmux")])

    def test_move_last_pane_preserves_source_session_with_a_shell_window(self):
        result = self.run_wt("--background", "--move-pane", "%7", "feature/login",
                             WT_TEST_SOURCE_INFO="$1 1 1")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [call[1] for call in self.calls("tmux")]
        replacement = ["new-window", "-d", "-t", "$1:", "-c", str(self.repo)]
        self.assertIn(replacement, calls)
        self.assertLess(calls.index(replacement), next(i for i, c in enumerate(calls) if c[0] == "join-pane"))

    def test_move_pane_foreground_switches_only_after_layout_is_ready(self):
        result = self.run_wt("--move-pane", "%7", "feature/login")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("tmux")[-1][1], ["switch-client", "-t", "$42"])

    def test_move_pane_accepts_reordered_flags(self):
        result = self.run_wt("--move-pane", "%7", "--background", "feature/login")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("tmux")[-1][1][0], "select-pane")

    def test_move_pane_requires_exact_pane_id(self):
        for args in [("--move-pane",), ("--move-pane", "main:1", "feature/login"),
                     ("--move-pane", "%x", "feature/login")]:
            with self.subTest(args=args):
                result = self.run_wt(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("requires an exact tmux pane ID", result.stderr)
                self.assertFalse(self.log.exists())

    def test_move_pane_requires_tmux_even_with_background(self):
        result = self.run_wt("--background", "--move-pane", "%7", "feature/login", TMUX="")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_move_missing_pane_fails_before_creating_worktree(self):
        result = self.run_wt("--background", "--move-pane", "%7", "feature/login",
                             WT_TEST_PANE_MISSING="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot identify tmux pane", result.stderr)
        self.assertFalse(self.worktree.exists())
        self.assertEqual(self.calls("git"), [])

    def test_move_requires_editor_and_lazygit_before_creating_worktree(self):
        for name in ("nvim", "lazygit"):
            with self.subTest(command=name):
                binary = self.repo.parent / "bin" / name
                contents = binary.read_text()
                binary.unlink()
                try:
                    result = self.run_wt("--background", "--move-pane", "%7", "feature/login",
                                         PATH=str(binary.parent) + ":/usr/bin:/bin")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"wt requires {name}", result.stderr)
                    self.assertFalse(self.worktree.exists())
                    self.assertFalse(self.log.exists())
                finally:
                    binary.write_text(contents)
                    binary.chmod(0o755)

    def test_move_setup_failures_never_move_pane_or_report_success(self):
        for failure in ("WT_TEST_ADD_FAIL", "WT_TEST_ASDF_EXIT", "WT_TEST_SESSION_FAIL", "WT_TEST_SPLIT_FAIL"):
            with self.subTest(failure=failure):
                result = self.run_wt("--background", "--move-pane", "%7", "feature/login",
                                     WT_TEST_TOOL_VERSIONS="1", **{failure: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("join-pane", [call[1][0] for call in self.calls("tmux")])
                self.assertNotIn("Tmux session:", result.stdout)
                if self.worktree.exists():
                    for child in self.worktree.iterdir():
                        child.unlink()
                    self.worktree.rmdir()
                self.log.unlink()

    def test_move_join_failure_does_not_report_success(self):
        result = self.run_wt("--background", "--move-pane", "%7", "feature/login",
                             WT_TEST_JOIN_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls("tmux")[-1][1][0], "join-pane")
        self.assertTrue(self.worktree.is_dir())
        self.assertNotIn("Tmux session:", result.stdout)

    def test_still_requires_tmux(self):
        result = self.run_wt(TMUX="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wt must be run inside tmux", result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
