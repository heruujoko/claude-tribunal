import os
from pathlib import Path
import shutil
import subprocess
import unittest


SKILL = Path(__file__).resolve().parents[1] / "skills/setup-cloudflare/SKILL.md"
VARIABLES = ("CCV_PROVIDER", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")


class SetupSkillTests(unittest.TestCase):
    def check_status_command(self, shell):
        executable = shutil.which(shell)
        if not executable:
            self.skipTest(f"{shell} is not installed")
        section = SKILL.read_text().split("## Step 4", 1)[1].split("## Step 5", 1)[0]
        start = section.index("python3 -c '")
        end = section.index("'\n", start) + 1
        command = section[start:end]
        cases = ({}, dict.fromkeys(VARIABLES, "dummy-secret"),
                 {"CCV_PROVIDER": "cloudflare", "CLOUDFLARE_ACCOUNT_ID": "dummy-account"})
        for values in cases:
            with self.subTest(present=sorted(values)):
                # Do not inherit credentials or load user shell profiles.
                env = {"PATH": os.environ.get("PATH", os.defpath), **values}
                args = [executable, "--no-config"] if shell == "fish" else [executable, "-f"]
                proc = subprocess.run(args + ["-c", command], env=env,
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stderr, "")
                expected = [f"{v}: {'set' if v in values else 'MISSING'}" for v in VARIABLES]
                self.assertEqual(proc.stdout.splitlines(), expected)

    def test_bash_status_command(self):
        self.check_status_command("bash")

    def test_zsh_status_command(self):
        self.check_status_command("zsh")

    def test_fish_status_command(self):
        self.check_status_command("fish")


if __name__ == "__main__":
    unittest.main()
