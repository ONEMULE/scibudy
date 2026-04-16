from research_mcp.models import LiteratureResult
from research_mcp.ranking import dedupe_and_rank


def test_dedupe_merges_duplicate_doi_and_keeps_richer_fields():
    left = LiteratureResult(
        title="A test paper",
        abstract="Detailed abstract",
        authors=["Alice"],
        year=2025,
        doi="10.1000/example",
        source="OpenAlex",
        source_id="OA1",
        landing_url="https://openalex.org/W1",
    )
    right = LiteratureResult(
        title="A test paper",
        authors=["Alice", "Bob"],
        year=2025,
        doi="https://doi.org/10.1000/example",
        source="Crossref",
        source_id="CR1",
        landing_url="https://doi.org/10.1000/example",
        citation_count=120,
    )

    ranked = dedupe_and_rank([left, right], query="test paper", sort="relevance", limit=10)

    assert len(ranked) == 1
    assert ranked[0].citation_count == 120
    assert ranked[0].abstract == "Detailed abstract"
    assert ranked[0].extras["merged_sources"] == ["Crossref", "OpenAlex"]


def test_sbi_calibration_ranking_promotes_domain_specific_paper():
    generic_high_citation = LiteratureResult(
        title="SciPy 1.0: fundamental algorithms for scientific computing in Python",
        abstract="General scientific computing methods and software.",
        year=2020,
        source="OpenAlex",
        citation_count=20000,
    )
    domain_specific = LiteratureResult(
        title="Calibrating Neural Simulation-Based Inference with Differentiable Coverage Probability",
        abstract="We study posterior calibration and coverage for simulation-based inference.",
        year=2024,
        source="Semantic Scholar",
        citation_count=40,
        extras={"fields_of_study": ["Machine Learning", "Statistics"], "influential_citation_count": 5},
    )

    ranked = dedupe_and_rank(
        [generic_high_citation, domain_specific],
        query="calibrations methods in simulation-based inference",
        sort="relevance",
        limit=2,
    )

    assert ranked[0].title == domain_specific.title
