# Usage Examples

## Minimal search

```bash
scibudy search "simulation-based calibration"
```

## Build a local library

```bash
scibudy collect "simulation-based calibration" --target-dir ~/Desktop/sbc-library
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
Use search_literature to find recent papers on simulation-based calibration, then organize the strongest ones into a local library.
```
