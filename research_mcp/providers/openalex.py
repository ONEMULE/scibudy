from __future__ import annotations

from research_mcp.models import LiteratureResult
from research_mcp.providers.base import BaseProvider
from research_mcp.utils import canonical_doi, extract_authors_from_names, first_non_empty, openalex_abstract, pick_url, safe_int


class OpenAlexProvider(BaseProvider):
    name = "OpenAlex"
    cache_ttl_sec = 6 * 60 * 60
    min_interval_sec = 0.35
    enabled_flag = "enable_openalex"

    def search(self, query: str, limit: int, sort: str) -> list[LiteratureResult]:
        params = {"search": query, "per-page": limit}
        if sort == "recent":
            params["sort"] = "publication_date:desc"
        if self.settings.openalex_api_key:
            params["api_key"] = self.settings.openalex_api_key
        data, _ = self.client.get_json(
            provider_name=self.name,
            url="https://api.openalex.org/works",
            params=params,
            ttl_sec=self.cache_ttl_sec,
            min_interval_sec=self.min_interval_sec,
        )
        results: list[LiteratureResult] = []
        for item in data.get("results", []):
            primary_location = item.get("primary_location") or {}
            best_oa_location = item.get("best_oa_location") or {}
            source = primary_location.get("source") or {}
            open_access = item.get("open_access") or {}
            results.append(
                LiteratureResult(
                    title=item.get("display_name"),
                    abstract=openalex_abstract(item.get("abstract_inverted_index")),
                    authors=extract_authors_from_names(item.get("authorships", [])),
                    year=safe_int(item.get("publication_year")),
                    published_date=item.get("publication_date"),
                    doi=canonical_doi(item.get("doi")),
                    source=self.name,
                    source_id=item.get("id"),
                    landing_url=first_non_empty(item.get("doi"), primary_location.get("landing_page_url"), item.get("id")),
                    pdf_url=pick_url(first_non_empty(best_oa_location.get("pdf_url"), primary_location.get("pdf_url"))),
                    journal=source.get("display_name"),
                    publisher=source.get("host_organization_name"),
                    citation_count=safe_int(item.get("cited_by_count")),
                    is_open_access=open_access.get("is_oa"),
                    open_access_url=pick_url(first_non_empty(best_oa_location.get("landing_page_url"), primary_location.get("landing_page_url"))),
                    license=first_non_empty(best_oa_location.get("license"), open_access.get("oa_status")),
                    extras={
                        "type": item.get("type"),
                        "venue": source.get("display_name"),
                        "host_organization": source.get("host_organization_name"),
                        "oa_status": open_access.get("oa_status"),
                        "topics": [topic.get("display_name") for topic in item.get("topics", []) if topic.get("display_name")],
                    },
                )
            )
        return results
