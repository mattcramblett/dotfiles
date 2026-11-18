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
    if args[0] == "rev-parse":
        print(os.environ["WT_TEST_REPO"] + "/.git")
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
elif command == "tmux":
    if args[0] == "has-session":
        sys.exit(0 if os.environ.get("WT_TEST_SESSION_EXISTS") else 1)
    elif args[0] == "new-session":
        sys.exit(1) if os.environ.get("WT_TEST_SESSION_FAIL") else print("$42")
    else:
        assert args == ["switch-client", "-t", "$42"], args
elif command == "asdf":
    assert args == ["install"], args
    sys.exit(int(os.environ.get("WT_TEST_ASDF_EXIT", "0")))
'''


class WorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wt tests ")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.repo = root / "repo"
        self.repo.mkdir()
        self.worktree = root / "repo-feature-login"
        self.log = root / "calls.jsonl"
        binaries = root / "bin"
        binaries.mkdir()
        for name in ("git", "tmux", "asdf"):
            stub = binaries / name
            stub.write_text(f"#!{sys.executable}\n" + STUB)
            stub.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "TMUX": "test-session",
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
        return [call for call in calls if command is None or call[0] == command]

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
                ["switch-client", "-t", "$42"],
            ],
        )
        commands = [call[0] for call in self.calls()]
        self.assertLess(commands.index("asdf"), len(commands) - 2)

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

    def test_existing_session_is_rejected_before_creating_worktree(self):
        result = self.run_wt(WT_TEST_SESSION_EXISTS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Tmux session already exists", result.stderr)
        self.assertFalse(self.worktree.exists())
        self.assertFalse(any(call[1][:2] == ["worktree", "add"] for call in self.calls("git")))

    def test_session_name_normalizes_dots_and_keeps_directory_name(self):
        result = self.run_wt("mattcramblett/feature.v2/login")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.calls("tmux")[-2][1]
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
        self.assertEqual(self.calls("tmux")[-1][1][0], "new-session")
        self.assertEqual(len(self.calls("tmux")), 2)
        self.assertEqual([call[0] for call in self.calls()][-2:], ["asdf", "tmux"])
        self.assertIn(f"Worktree: {self.worktree}", result.stdout)
        self.assertIn("Tmux session: repo-feature-login", result.stdout)

    def test_background_works_without_tmux_environment(self):
        result = self.run_wt("--background", "feature/login", TMUX="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.worktree.is_dir())
        self.assertEqual(self.calls("tmux")[-1][1][0], "new-session")
        self.assertEqual(len(self.calls("tmux")), 2)

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
                self.assertIn("Usage: wt [--background] <branch-name>", result.stderr)
                self.assertFalse(self.log.exists())

    def test_background_help_does_not_require_tmux(self):
        result = self.run_wt("--background", "--help", TMUX="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--background leaves the session detached", result.stdout)
        self.assertFalse(self.log.exists())

    def test_still_requires_tmux(self):
        result = self.run_wt(TMUX="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wt must be run inside tmux", result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
