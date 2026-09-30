import os
from pathlib import Path
import shutil
import subprocess
import unittest

from hooks import tribunal

SKILL = Path(__file__).resolve().parents[1] / "skills/setup-cloudflare/SKILL.md"
SCANNING_SKILL = Path(__file__).resolve().parents[1] / "skills/setup-scanning/SKILL.md"
VARIABLES = ("TRIBUNAL_PROVIDER", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")


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
                 {"TRIBUNAL_PROVIDER": "cloudflare", "CLOUDFLARE_ACCOUNT_ID": "dummy-account"})
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


class SetupScanningSkillTests(unittest.TestCase):
    def check_scan_command(self, shell):
        executable = shutil.which(shell)
        if not executable:
            self.skipTest(f"{shell} is not installed")
        section = SCANNING_SKILL.read_text().split("## Step 4", 1)[1]
        start = section.index("python3 -c '")
        end = section.index("'\n", start) + 1
        command = section[start:end]
        for values in ({}, {"TRIBUNAL_SCAN": ""}, {"TRIBUNAL_SCAN": "web"},
                       {"TRIBUNAL_SCAN": "skills,web"}, {"TRIBUNAL_SCAN": "off"},
                       {"TRIBUNAL_SCAN": "bogus"}):
            with self.subTest(values=values):
                env = {"PATH": os.environ.get("PATH", os.defpath), **values}
                args = [executable, "--no-config"] if shell == "fish" else [executable, "-f"]
                proc = subprocess.run(args + ["-c", command], env=env,
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stderr, "")
                expected = "scanning: " + (",".join(sorted(tribunal.scan_scopes(env))) or "off")
                self.assertEqual(proc.stdout.strip(), expected)

    def test_bash_scan_command(self):
        self.check_scan_command("bash")

    def test_zsh_scan_command(self):
        self.check_scan_command("zsh")

    def test_fish_scan_command(self):
        self.check_scan_command("fish")

    def test_frontmatter_name(self):
        self.assertIn("name: setup-scanning\n", SCANNING_SKILL.read_text().split("---")[1] + "\n")


if __name__ == "__main__":
    unittest.main()
