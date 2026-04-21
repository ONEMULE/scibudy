from research_mcp.service import ResearchService
from research_mcp.settings import Settings
import research_mcp.service as service_module
import os


class StubProvider:
    def __init__(self, name, enabled_flag="", required_settings=(), ready=True, message=None):
        self.name = name
        self.enabled_flag = enabled_flag
        self.required_settings = required_settings
        self._ready = ready
        self._message = message

    def ready(self):
        return self._ready, self._message


class StubResolver:
    name = "Unpaywall"
    required_settings = (("UNPAYWALL_EMAIL", "unpaywall_email"),)

    def ready(self):
        return False, "missing UNPAYWALL_EMAIL"


def test_health_check_reports_missing_credentials(tmp_path):
    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        CORE_API_KEY="",
        UNPAYWALL_EMAIL="",
    )
    service = ResearchService(
        settings=settings,
        providers={
            "core": StubProvider(
                "CORE",
                enabled_flag="enable_core",
                required_settings=(("CORE_API_KEY", "core_api_key"),),
                ready=False,
                message="missing CORE_API_KEY",
            )
        },
        oa_resolver=StubResolver(),
    )

    health = service.health_check()

    assert health.status == "degraded"
    assert any(item.provider == "CORE" and item.missing_credentials == ["CORE_API_KEY"] for item in health.provider_statuses)
    assert any(item.provider == "Unpaywall" and item.missing_credentials == ["UNPAYWALL_EMAIL"] for item in health.provider_statuses)


def test_health_check_does_not_degrade_for_ready_public_provider(tmp_path):
    settings = Settings(
        RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
        SEMANTIC_SCHOLAR_API_KEY="",
        UNPAYWALL_EMAIL="configured@example.com",
    )
    service = ResearchService(
        settings=settings,
        providers={
            "semanticscholar": StubProvider(
                "Semantic Scholar",
                enabled_flag="enable_semantic_scholar",
                required_settings=(("SEMANTIC_SCHOLAR_API_KEY", "semantic_scholar_api_key"),),
                ready=True,
                message="using public shared pool via bulk search",
            )
        },
        oa_resolver=type(
            "ReadyResolver",
            (),
            {
                "name": "Unpaywall",
                "required_settings": (("UNPAYWALL_EMAIL", "unpaywall_email"),),
                "ready": staticmethod(lambda: (True, None)),
            },
        )(),
    )

    health = service.health_check()

    assert health.status == "ok"
    assert any(
        item.provider == "Semantic Scholar"
        and item.ready is True
        and item.missing_credentials == ["SEMANTIC_SCHOLAR_API_KEY"]
        for item in health.provider_statuses
    )
    assert not any("SEMANTIC_SCHOLAR_API_KEY" in suggestion for suggestion in health.suggestions)


def test_security_check_warns_for_broad_env_permissions(tmp_path, monkeypatch):
    if os.name == "nt":
        return
    env_file = tmp_path / ".env"
    env_file.write_text('OPENALEX_API_KEY="x"\n', encoding="utf-8")
    env_file.chmod(0o644)
    codex_config = tmp_path / "config.toml"
    codex_config.write_text("[mcp_servers.research]\n", encoding="utf-8")
    monkeypatch.setattr(service_module, "ENV_FILE", env_file)
    monkeypatch.setattr(service_module, "CODEX_CONFIG_FILE", codex_config)
    monkeypatch.setattr(service_module, "APP_HOME", tmp_path / "app")
    service = ResearchService(settings=Settings(RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db")), providers={}, oa_resolver=StubResolver())

    response = service.security_check()

    assert response.status == "warning"
    assert any(check.id == "env_permissions" and check.status == "warning" for check in response.checks)


def test_security_check_flags_suspicious_codex_secret(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    env_file.chmod(0o600)
    codex_config = tmp_path / "config.toml"
    codex_config.write_text('OPENAI_API_KEY = "sk-test1234567890abcdef"\n', encoding="utf-8")
    monkeypatch.setattr(service_module, "ENV_FILE", env_file)
    monkeypatch.setattr(service_module, "CODEX_CONFIG_FILE", codex_config)
    monkeypatch.setattr(service_module, "APP_HOME", tmp_path / "app")
    service = ResearchService(settings=Settings(RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db")), providers={}, oa_resolver=StubResolver())

    response = service.security_check()

    assert any(check.id == "codex_config_secrets" and check.status == "warning" for check in response.checks)


def test_security_check_errors_for_dangerous_app_home(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    env_file.chmod(0o600)
    codex_config = tmp_path / "config.toml"
    codex_config.write_text("[mcp_servers.research]\n", encoding="utf-8")
    monkeypatch.setattr(service_module, "ENV_FILE", env_file)
    monkeypatch.setattr(service_module, "CODEX_CONFIG_FILE", codex_config)
    dangerous_root = service_module.Path(service_module.Path.cwd().anchor or "/")
    monkeypatch.setattr(service_module, "APP_HOME", dangerous_root)
    service = ResearchService(settings=Settings(RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db")), providers={}, oa_resolver=StubResolver())

    response = service.security_check()

    assert response.status == "error"
    assert any(check.id == "app_home_safety" and check.status == "error" for check in response.checks)
