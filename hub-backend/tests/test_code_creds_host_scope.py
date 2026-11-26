"""The Git credential helper only answers for the host this execution may reach."""
import os
import subprocess
import unittest

from app.services import code_creds

TOKEN = "fixture-helper-token"


def ask_helper(helper: str, host: str, allowed: str) -> str:
    """Ask the credential helper about one host, the way git does."""
    env = dict(os.environ)
    env["GIT_CONFIG_COUNT"] = "2"
    env["GIT_CONFIG_KEY_0"] = "credential.helper"
    env["GIT_CONFIG_VALUE_0"] = ""
    env["GIT_CONFIG_KEY_1"] = "credential.helper"
    env["GIT_CONFIG_VALUE_1"] = helper
    env["SODUWORK_GIT_USER"] = "fixture-user"
    env["SODUWORK_GIT_TOKEN"] = TOKEN
    env["SODUWORK_GIT_ALLOWED_HOSTS"] = allowed
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input=f"protocol=https\nhost={host}\n\n",
        env=env, capture_output=True, text=True, timeout=30)
    return proc.stdout


def helper_from_env(env: dict) -> str:
    """Return the credential.helper this environment installs."""
    count = int(env.get("GIT_CONFIG_COUNT") or 0)
    for index in range(count):
        if env.get(f"GIT_CONFIG_KEY_{index}") == "credential.helper":
            value = env.get(f"GIT_CONFIG_VALUE_{index}") or ""
            if value:
                return value
    return ""


class CredentialHelperHostScopeTests(unittest.TestCase):
    def test_allowed_host_is_derived_from_the_repository_url(self):
        self.assertEqual(code_creds._allowed_hosts("https://git.internal.corp/team/repo.git"),
                         "git.internal.corp")
        self.assertEqual(code_creds._allowed_hosts("https://user@git.internal.corp:8443/team/repo.git"),
                         "git.internal.corp:8443")
        self.assertEqual(code_creds._allowed_hosts("git@git.internal.corp:team/repo.git"),
                         "git.internal.corp")
        self.assertEqual(code_creds._allowed_hosts(""), "")
        self.assertEqual(code_creds._allowed_hosts("   "), "")

    def test_allowed_host_keeps_the_port_because_git_reports_it(self):
        # git passes the port through to the helper, so the allow-list has to
        # keep it or a repository on a custom port would never authenticate.
        helper = code_creds._helper_script()
        allowed = code_creds._allowed_hosts("https://git.internal.corp:8443/team/repo.git")
        self.assertIn(TOKEN, ask_helper(helper, "git.internal.corp:8443", allowed))
        self.assertNotIn(TOKEN, ask_helper(helper, "git.internal.corp", allowed))

    def test_helper_returns_credentials_only_for_the_allowed_host(self):
        helper = code_creds._helper_script()
        allowed = code_creds._allowed_hosts("https://git.internal.corp/team/repo.git")
        self.assertIn(TOKEN, ask_helper(helper, "git.internal.corp", allowed))
        for host in ("gitlab.com", "attacker.example", "evil.invalid"):
            with self.subTest(host=host):
                self.assertNotIn(TOKEN, ask_helper(helper, host, allowed))

    def test_empty_allow_list_withholds_credentials_from_every_host(self):
        helper = code_creds._helper_script()
        for host in ("git.internal.corp", "attacker.example"):
            with self.subTest(host=host):
                self.assertNotIn(TOKEN, ask_helper(helper, host, ""))

    def test_env_for_scopes_the_helper_to_the_given_url(self):
        git = {"name": "Fixture", "email": "fixture@example.test",
               "user": "fixture-user", "token": TOKEN, "key": ""}
        env = code_creds.env_for({}, git, ref="fixture",
                                  url="https://git.internal.corp/team/repo.git")
        self.assertEqual(env["SODUWORK_GIT_ALLOWED_HOSTS"], "git.internal.corp")
        helper = helper_from_env(env)
        self.assertTrue(helper, "环境里应当装有 credential.helper")
        self.assertIn(TOKEN, ask_helper(helper, "git.internal.corp", env["SODUWORK_GIT_ALLOWED_HOSTS"]))
        self.assertNotIn(TOKEN, ask_helper(helper, "attacker.example", env["SODUWORK_GIT_ALLOWED_HOSTS"]))

    def test_env_for_without_a_url_withholds_credentials(self):
        git = {"name": "Fixture", "email": "fixture@example.test",
               "user": "fixture-user", "token": TOKEN, "key": ""}
        env = code_creds.env_for({}, git, ref="fixture")
        self.assertEqual(env.get("SODUWORK_GIT_ALLOWED_HOSTS", ""), "")
        helper = helper_from_env(env)
        self.assertNotIn(TOKEN, ask_helper(helper, "git.internal.corp", ""))


if __name__ == "__main__":
    unittest.main()
