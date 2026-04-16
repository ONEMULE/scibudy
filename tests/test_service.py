import time

from research_mcp.errors import ProviderRequestError
from research_mcp.models import LiteratureResult
from research_mcp.service import ResearchService
from research_mcp.settings import Settings


class StubProvider:
    def __init__(self, name, results=None, error=None, ready=True, message=None, delay=0.0):
        self.name = name
        self._results = results or []
        self._error = error
        self._ready = ready
        self._message = message
        self._delay = delay

    def ready(self):
        return self._ready, self._message

    def search(self, query, limit, sort):
        if self._delay:
            time.sleep(self._delay)
        if self._error:
            raise self._error
        return self._results


class StubResolver:
    def ready(self):
        return False, "missing UNPAYWALL_EMAIL"


def test_service_returns_partial_results_when_one_provider_fails(tmp_path):
    ok_provider = StubProvider(
        "OpenAlex",
        results=[
            LiteratureResult(
                title="Useful paper",
                source="OpenAlex",
                source_id="W1",
                year=2025,
            )
        ],
    )
    failing_provider = StubProvider("Crossref", error=ProviderRequestError("boom"))
    service = ResearchService(
        settings=Settings(RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db")),
        providers={"openalex": ok_provider, "crossref": failing_provider},
        oa_resolver=StubResolver(),
    )

    response = service._run_provider_group(
        query="useful paper",
        provider_names=["openalex", "crossref"],
        mode="general",
        limit=5,
        sort="relevance",
    )

    assert response.result_count == 1
    assert any(item.status == "error" and item.provider == "Crossref" for item in response.provider_coverage)
    assert all(item.elapsed_ms is None or item.elapsed_ms >= 0 for item in response.provider_coverage)
    assert response.results[0].title == "Useful paper"


def test_service_times_out_slow_provider_without_losing_fast_results(tmp_path):
    fast_provider = StubProvider(
        "OpenAlex",
        results=[LiteratureResult(title="Fast calibration paper", source="OpenAlex", source_id="W1")],
    )
    slow_provider = StubProvider("CORE", results=[LiteratureResult(title="Slow paper", source="CORE", source_id="C1")], delay=0.15)
    service = ResearchService(
        settings=Settings(
            RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db"),
            RESEARCH_MCP_PROVIDER_TIMEOUT_SEC=0.05,
            RESEARCH_MCP_SEARCH_TOTAL_TIMEOUT_SEC=0.05,
        ),
        providers={"openalex": fast_provider, "core": slow_provider},
        oa_resolver=StubResolver(),
    )

    response = service._run_provider_group(
        query="simulation based calibration",
        provider_names=["openalex", "core"],
        mode="general",
        limit=5,
        sort="relevance",
    )

    assert response.result_count == 1
    assert response.results[0].title == "Fast calibration paper"
    assert any(item.provider == "CORE" and item.status == "error" and "timed out" in (item.message or "") for item in response.provider_coverage)


def test_resolve_open_access_reports_configuration_error(tmp_path):
    service = ResearchService(
        settings=Settings(RESEARCH_MCP_CACHE_DB_PATH=str(tmp_path / "state.db")),
        providers={},
        oa_resolver=StubResolver(),
    )

    response = service.resolve_open_access("10.1000/example")

    assert response.status == "error"
    assert response.message == "missing UNPAYWALL_EMAIL"
