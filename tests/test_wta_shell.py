import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "zsh/.config/zsh/tools.zsh"
ZSH = shutil.which("zsh")


@unittest.skipUnless(ZSH, "zsh is not installed")
class AgentWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wta wrappers ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"
        self.env = {**os.environ, "HOME": str(self.root), "PATH": str(self.bin) + ":/usr/bin:/bin",
                    "WTA_TEST_LOG": str(self.log), "ASDF_NODEJS_VERSION": "repository-version"}
        self.env.pop("PI_DEFAULT_MODEL", None)
        (self.root / ".tool-versions").write_text("nodejs 22.0.0\n")
        self.stub("asdf", 'print(str(Path(os.environ["HOME"]) / "node") if sys.argv[-1] != "java" else "/java")')
        self.stub("wt-workspace", 'sys.exit(int(os.environ.get("WTA_TRACK_EXIT", "0")))')
        self.stub("claude", 'print("received:" + sys.stdin.read()); sys.exit(7)')
        node = self.root / "node/bin"
        node.mkdir(parents=True)
        self.stub("node", 'print("received:" + sys.stdin.read()); sys.exit(9)', directory=node)
        self.stub("pi", "", directory=node)

    def stub(self, name, script, directory=None):
        path = (directory or self.bin) / name
        path.write_text(f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
                        'with open(os.environ["WTA_TEST_LOG"], "a") as log:\n'
                        '    log.write(json.dumps([Path(sys.argv[0]).name, sys.argv[1:], '
                        'os.environ.get("ASDF_NODEJS_VERSION")]) + "\\n")\n' + script + "\n")
        path.chmod(0o755)

    def invoke(self, agent, *args, **env):
        return subprocess.run([ZSH, "-dfc", 'source "$1"; shift; "$@"', "test", str(TOOLS), agent, *args],
                              env={**self.env, **env}, input="user input", capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_claude_preserves_arguments_stdin_output_and_exit_status(self):
        result = self.invoke("claude", "--resume", "a 'quoted' task")
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(result.stdout, "received:user input\n")
        self.assertEqual([call[:2] for call in self.calls() if call[0] != "asdf"],
                         [["wt-workspace", ["remember-agent", "claude"]],
                          ["claude", ["--resume", "a 'quoted' task"]]])

    def test_pi_preserves_model_arguments_node_and_environment(self):
        result = self.invoke("pi", "--resume", "a task", PI_DEFAULT_MODEL="provider/model")
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(result.stdout, "received:user input\n")
        node = next(call for call in self.calls() if call[0] == "node")
        self.assertEqual(node[1], [str(self.root / "node/bin/pi"), "--model", "provider/model", "--resume", "a task"])
        self.assertIsNone(node[2])
        self.assertIn(["wt-workspace", ["remember-agent", "pi"], None], self.calls())

    def test_bookkeeping_failure_does_not_interrupt_launch(self):
        result = self.invoke("claude", "task", WTA_TRACK_EXIT="1")
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(result.stdout, "received:user input\n")

    def test_missing_tracker_does_not_interrupt_launch(self):
        (self.bin / "wt-workspace").unlink()
        result = self.invoke("pi", "task")
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertNotIn("wt-workspace", result.stderr)

    def test_missing_agent_is_not_recorded(self):
        (self.bin / "claude").unlink()
        result = self.invoke("claude")
        self.assertEqual(result.returncode, 127)
        self.assertFalse(any(call[0] == "wt-workspace" for call in self.calls()))
        (self.root / "node/bin/pi").unlink()
        result = self.invoke("pi")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(any(call[0] == "wt-workspace" for call in self.calls()))


if __name__ == "__main__":
    unittest.main()
