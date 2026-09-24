from pathlib import Path
import re
import unittest

from tools.check import ROOT


OPENCLAW_SCRIPTS = ROOT / "scripts" / "openclaw"


class OpenClawInstallerTests(unittest.TestCase):
    def read_script(self, name: str) -> str:
        return (OPENCLAW_SCRIPTS / name).read_text(encoding="utf-8")

    def test_installers_pin_the_same_exact_release(self) -> None:
        versions = []
        for name in ("Install-OpenClawSuperAdmin.ps1", "Install-OpenClawNode.ps1"):
            content = self.read_script(name)
            match = re.search(
                r'\[string\]\$OpenClawVersion = "(\d{4}\.\d+\.\d+)"', content
            )
            self.assertIsNotNone(match, name)
            versions.append(match.group(1))

        self.assertEqual(versions, ["2026.6.34", "2026.6.34"])

    def test_installation_does_not_pipe_remote_code_to_powershell(self) -> None:
        content = "\n".join(
            path.read_text(encoding="utf-8")
            for path in OPENCLAW_SCRIPTS.glob("*.ps*1")
        ).lower()
        self.assertNotIn("invoke-webrequest", content)
        self.assertNotIn("invoke-expression", content)
        self.assertNotIn("| iex", content)
        self.assertNotIn("openclaw@latest", content)

    def test_node_installer_disables_remote_execution(self) -> None:
        content = self.read_script("Install-OpenClawNode.ps1")
        self.assertIn('"exec-policy", "preset", "deny-all"', content)
        self.assertIn('"nodeHost.browserProxy.enabled", "false"', content)
        self.assertIn('"nodeHost.autoUpdate.enabled", "false"', content)
        self.assertIn('"--commands", "device.status"', content)
        self.assertNotIn('"system.run"', content)

    def test_gateway_denies_mutating_node_surfaces(self) -> None:
        content = self.read_script("Install-OpenClawSuperAdmin.ps1")
        for command in (
            "browser.proxy",
            "computer.act",
            "mcp.tools.call.v1",
            "system.run",
            "system.which",
        ):
            self.assertIn(f'"{command}"', content)
        self.assertIn('"gateway.nodes.pluginTools.enabled", "false"', content)

    def test_gateway_secret_uses_file_secret_reference(self) -> None:
        content = self.read_script("Install-OpenClawSuperAdmin.ps1")
        self.assertIn('"--ref-provider", "cfmi"', content)
        self.assertIn("Write-CfmiJsonFile", content)
        self.assertNotIn('"config", "set", "gateway.auth.token", $token', content)

    def test_superadmin_has_no_node_control_tool(self) -> None:
        installer = self.read_script("Install-OpenClawSuperAdmin.ps1")
        allowed_tools = re.search(
            r'\$allowedTools = @\((.*?)\) \| ConvertTo-Json', installer, re.DOTALL
        )
        denied_tools = re.search(
            r'\$deniedTools = @\((.*?)\) \| ConvertTo-Json', installer, re.DOTALL
        )
        self.assertIsNotNone(allowed_tools)
        self.assertIsNotNone(denied_tools)
        self.assertNotIn('"nodes"', allowed_tools.group(1))
        self.assertIn('"nodes"', denied_tools.group(1))

        content = self.read_script("templates/SuperAdmin-AGENTS.md")
        normalized_content = " ".join(content.split())
        self.assertIn("Do not execute commands", content)
        self.assertIn("Do not restart, stop, resume, re-arm, or reassign", content)
        self.assertIn("live, stale, unavailable, or last known", normalized_content)
        self.assertIn("this agent has no node tool", content)


if __name__ == "__main__":
    unittest.main()
