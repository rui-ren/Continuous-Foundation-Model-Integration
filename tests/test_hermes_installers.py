from pathlib import Path
import re
import unittest

from tools.check import ROOT


INSTALLER_SCRIPTS = ROOT / "scripts" / "openclaw"
FLEET_CONFIG_SCRIPT = (
    ROOT / "scripts" / "hermes" / "Configure-HermesFleetObserver.ps1"
)
TEAMS_BOT_SCRIPT = ROOT / "scripts" / "hermes" / "New-HermesTeamsBot.ps1"


class HermesInstallerTests(unittest.TestCase):
    def read_script(self, name: str) -> str:
        return (INSTALLER_SCRIPTS / name).read_text(encoding="utf-8")

    def test_central_installer_pins_an_exact_hermes_release(self) -> None:
        content = self.read_script("Install-OpenClawSuperAdmin.ps1")
        match = re.search(
            r'\[string\]\$HermesVersion = "(\d+\.\d+\.\d+)"', content
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "0.21.5")
        commit = re.search(
            r'\[string\]\$HermesCommit = "([a-f0-9]{40})"', content
        )
        self.assertIsNotNone(commit)
        self.assertEqual(
            commit.group(1), "749220ef0007f8d87bd1531f1c24b0fe93816385"
        )
        helper = self.read_script("Hermes.Install.psm1")
        self.assertIn(
            "git+https://github.com/NousResearch/hermes-agent.git@$Commit", helper
        )
        self.assertIn('"--upgrade"', helper)
        self.assertIn("read_text('direct_url.json')", helper)
        self.assertIn('$provenance["vcs_info"]["commit_id"] -cne $Commit.ToLowerInvariant()', helper)
        self.assertIn('$provenance["url"] -cne "https://github.com/NousResearch/hermes-agent.git"', helper)

    def test_version_check_requires_complete_token(self) -> None:
        helper = self.read_script("Hermes.Install.psm1")
        self.assertIn("(?<![A-Za-z0-9.+-])v$([Regex]::Escape($Version))(?![A-Za-z0-9.+-])", helper)
        self.assertNotIn('-notmatch [Regex]::Escape("v$Version")', helper)

    def test_installer_only_describes_its_own_actions(self) -> None:
        installer = self.read_script("Install-OpenClawSuperAdmin.ps1")
        self.assertIn("This invocation does not install OpenClaw or deploy Hermes to fleet nodes.", installer)
        self.assertNotIn("OpenClaw is not installed", installer)

    def test_installation_does_not_pipe_remote_code_to_powershell(self) -> None:
        content = "\n".join(
            path.read_text(encoding="utf-8")
            for path in INSTALLER_SCRIPTS.glob("*.ps*1")
        ).lower()
        self.assertNotIn("invoke-webrequest", content)
        self.assertNotIn("invoke-restmethod", content)
        self.assertNotIn("invoke-expression", content)
        self.assertNotIn("| iex", content)
        self.assertNotIn("| bash", content)

    def test_active_installers_do_not_install_or_invoke_openclaw(self) -> None:
        content = "\n".join(
            self.read_script(name)
            for name in ("Install-OpenClawSuperAdmin.ps1", "Install-OpenClawNode.ps1")
        ).lower()
        self.assertNotIn("npm install", content)
        self.assertNotIn("openclaw@", content)
        self.assertNotIn("invoke-cfminativecommand openclaw", content)

    def test_central_installer_uses_isolated_venv_and_safety_defaults(self) -> None:
        helper = self.read_script("Hermes.Install.psm1")
        installer = self.read_script("Install-OpenClawSuperAdmin.ps1")
        self.assertIn('"cfmi-runtime"', helper)
        self.assertIn('"-m", "venv"', helper)
        self.assertIn('Set-Item "Env:$gitConfigKeyName" "core.longpaths"', helper)
        self.assertIn('Set-Item "Env:$gitConfigValueName" "true"', helper)
        self.assertIn('@("approvals.mode", "manual")', helper)
        self.assertIn('@("approvals.cron_mode", "deny")', helper)
        self.assertIn('@("approvals.single_query_mode", "deny")', helper)
        self.assertIn('@("approvals.unattended_mode", "deny")', helper)
        self.assertIn('"templates\\HermesObserver-AGENTS.md"', installer)
        self.assertIn("chat --toolsets clarify", installer)

    def test_node_installer_fails_closed_without_installing_an_agent(self) -> None:
        content = self.read_script("Install-OpenClawNode.ps1")
        self.assertIn("throw @\"", content)
        self.assertIn("no OpenClaw-compatible Node Host", content)
        self.assertIn("Do not install an agent runtime on fleet nodes", content)
        self.assertNotIn("Install-CfmiHermesPackage", content)
        self.assertNotIn("pip", content)
        self.assertNotIn("git clone", content)

    def test_observer_instructions_forbid_control_surfaces(self) -> None:
        content = self.read_script("templates/HermesObserver-AGENTS.md")
        normalized = " ".join(content.split())
        self.assertIn("Do not execute commands", content)
        self.assertIn("Do not claim to have queried live node state", content)
        self.assertIn("live, stale, unavailable, or last known", normalized)
        self.assertIn("Do not restart, stop, resume, re-arm, or reassign", content)
        self.assertIn("Never request or expose credentials", content)

    def test_fleet_observer_subagents_are_bounded_and_read_only(self) -> None:
        content = FLEET_CONFIG_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"delegation.max_concurrent_children" "4"', content)
        self.assertIn('"delegation.max_spawn_depth" "1"', content)
        self.assertIn('"delegation.orchestrator_enabled" "false"', content)
        self.assertIn('"delegation.oneshot_max_children" "2"', content)
        self.assertIn('"delegation.max_iterations" "60"', content)
        self.assertIn('"delegation.child_timeout_seconds" "600"', content)
        self.assertIn('"delegation.subagent_auto_approve" "false"', content)
        self.assertIn('"delegation.inherit_mcp_toolsets" "true"', content)
        self.assertIn(
            '"mcp_servers.cfmi_fleet_status.trust" "full"', content
        )
        self.assertNotIn(
            '"mcp_servers.cfmi_fleet_status.trust" "untrusted"', content
        )
        self.assertIn(
            '@("clarify", "delegation", "cfmi_fleet_status")', content
        )
        self.assertIn(
            '@("clarify", "cfmi_fleet_status")', content
        )
        self.assertNotIn('"mcp-cfmi_fleet_status"', content)
        self.assertIn(
            "tools enable --platform cli clarify delegation", content
        )
        self.assertIn("tools enable --platform teams clarify", content)
        self.assertNotIn('"terminal"', content)
        self.assertNotIn('"file"', content)

    def test_teams_bot_provisioning_requires_governed_inputs(self) -> None:
        content = TEAMS_BOT_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("[string]$ServiceManagementReference", content)
        self.assertIn("[uri]$MessagingEndpoint", content)
        self.assertIn(
            '"--service-management-reference",',
            content,
        )
        self.assertIn('"SingleTenant"', content)
        self.assertIn('"F0"', content)
        self.assertIn('TEAMS_HOST = "127.0.0.1"', content)
        self.assertIn('TEAMS_ALLOW_ALL_USERS = "false"', content)
        self.assertIn('TEAMS_REQUIRE_MENTION = "true"', content)
        self.assertIn("Hermes gateway: not started", content)
        self.assertNotIn("gateway start", content)
        self.assertNotIn("gateway install", content)


if __name__ == "__main__":
    unittest.main()
