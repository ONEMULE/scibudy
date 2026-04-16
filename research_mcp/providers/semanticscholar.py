from __future__ import annotations

from research_mcp.models import LiteratureResult
from research_mcp.providers.base import BaseProvider
from research_mcp.utils import canonical_doi, extract_authors_from_names, first_non_empty, normalize_whitespace, pick_url, safe_int


class SemanticScholarProvider(BaseProvider):
    name = "Semantic Scholar"
    cache_ttl_sec = 6 * 60 * 60
    min_interval_sec = 1.0
    enabled_flag = "enable_semantic_scholar"
    required_settings = (("SEMANTIC_SCHOLAR_API_KEY", "semantic_scholar_api_key"),)

    def ready(self) -> tuple[bool, str | None]:
        if not self.settings.enable_semantic_scholar:
            return False, "disabled by configuration"
        if self.settings.semantic_scholar_api_key:
            return True, None
        if self.settings.allow_public_semantic_scholar:
            return True, "using public shared pool via bulk search"
        return False, "missing SEMANTIC_SCHOLAR_API_KEY"

    def search(self, query: str, limit: int, sort: str) -> list[LiteratureResult]:
        has_api_key = bool(self.settings.semantic_scholar_api_key)
        url = "https://api.semanticscholar.org/graph/v1/paper/search" if has_api_key else "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
        data, _ = self.client.get_json(
            provider_name=self.name,
            url=url,
            params={
                "query": query,
                "limit": limit,
                "fields": "paperId,title,year,authors,citationCount,influentialCitationCount,referenceCount,url,abstract,externalIds,openAccessPdf,journal,publicationDate,publicationTypes,venue,fieldsOfStudy",
            },
            headers={"x-api-key": self.settings.semantic_scholar_api_key} if has_api_key else None,
            ttl_sec=self.cache_ttl_sec,
            min_interval_sec=self.min_interval_sec,
        )
        results: list[LiteratureResult] = []
        for item in data.get("data", []):
            external_ids = item.get("externalIds") or {}
            journal = item.get("journal") or {}
            open_access_pdf = item.get("openAccessPdf") or {}
            results.append(
                LiteratureResult(
                    title=normalize_whitespace(item.get("title")),
                    abstract=normalize_whitespace(item.get("abstract")),
                    authors=extract_authors_from_names(item.get("authors", [])),
                    year=safe_int(item.get("year")),
                    published_date=item.get("publicationDate"),
                    doi=canonical_doi(external_ids.get("DOI")),
                    source=self.name,
                    source_id=item.get("paperId"),
                    landing_url=first_non_empty(item.get("url")),
                    pdf_url=pick_url(open_access_pdf),
                    journal=normalize_whitespace(journal.get("name")),
                    citation_count=safe_int(item.get("citationCount")),
                    is_open_access=bool(open_access_pdf) if open_access_pdf else None,
                    open_access_url=pick_url(open_access_pdf),
                    extras={
                        "mode": "authenticated" if has_api_key else "public-bulk",
                        "influential_citation_count": safe_int(item.get("influentialCitationCount")),
                        "reference_count": safe_int(item.get("referenceCount")),
                        "publication_types": item.get("publicationTypes") or [],
                        "venue": normalize_whitespace(item.get("venue")),
                        "fields_of_study": item.get("fieldsOfStudy") or [],
                    },
                )
            )
        return results
