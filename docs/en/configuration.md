# Configuration

## Secrets

User secrets live in the app-home `.env` file.

Common variables:

- `OPENALEX_API_KEY`
- `CROSSREF_MAILTO`
- `SEMANTIC_SCHOLAR_API_KEY`
- `NCBI_API_KEY`
- `UNPAYWALL_EMAIL`
- `CORE_API_KEY`
- `OPENAI_API_KEY`

## Analysis configuration

Use:

```bash
scibudy analysis-settings
scibudy analysis-update --analysis-mode hybrid --compute-backend local
```

Important analysis settings:

- `analysis_mode`
- `compute_backend`
- `chunk_size`
- `chunk_overlap`
- `forum_source_profile`
- local embedding/reranker model settings

## Domain profiles

Domain profiles affect only full-text synthesis. They do not constrain the scholarly search providers or the subject scope of `search_literature`.

Available synthesis profiles:

- `general`: default all-domain evidence extraction profile.
- `auto`: resolves a profile from the topic and records both the requested and resolved profile in the synthesis payload.
- `sbi_calibration`: example preset for simulation-based inference calibration evidence extraction.

Use:

```bash
scibudy profiles
scibudy synthesize-library <library_id> "causal inference robustness" --profile general
scibudy synthesize-library <library_id> "calibration in simulation-based inference" --profile sbi_calibration
```

## Runtime state

The app home stores:

- `.env`
- `state/`
- `analysis/`
- `library/`
- `ui/dist/`
