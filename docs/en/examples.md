# Usage Examples

## Minimal search

```bash
scibudy search "simulation-based calibration"
```

## Build a local library

```bash
scibudy collect "simulation-based calibration" --target-dir ~/Desktop/sbc-library
```

## Agent workflow

Use this when Codex or another agent should run the full loop with one call:

```bash
scibudy workflow "calibration methods in simulation-based inference" \
  --mode general \
  --limit 50 \
  --topic "calibration in simulation-based inference"
```

Preview the planned writes without executing:

```bash
scibudy workflow "calibration methods in simulation-based inference" --dry-run
```

Run a low-cost search and library setup pass:

```bash
scibudy workflow "calibration methods in simulation-based inference" --quality-mode fast
```

Check local safety and install readiness before agent automation:

```bash
scibudy security-audit
scibudy doctor --install-readiness
```

## Analyze a topic

```bash
scibudy ingest-library <library_id>
scibudy analyze-topic <library_id> calibration
```

## Search evidence

```bash
scibudy search-evidence <library_id> "posterior coverage"
```

## Open the UI

```bash
scibudy ui --open
```

## Codex prompt example

```text
Use research_workflow with query="calibration methods in simulation-based inference", mode="general", limit=50, synthesize=true.
```
