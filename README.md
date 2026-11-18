# Shared renovation and building-stock engine

Standalone copy of the maintained **v3.6 research module**, prepared for external testing on 18 November 2026. No cloud-drive access is required for the portable tests or bundled examples. Country forecasts and measured energy performance are not validated by software acceptance tests.

## Quick start

Tested locally with Python 3.12.14. Use Python 3.12 and a virtual environment:

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/run_tests.py
python scripts/run_example.py --output-dir outputs/acceptance
python scripts/run_example.py --donors --output-dir outputs/donors
```

The acceptance example is synthetic. The nine donor alternatives are conditional engineering profiles, not nine observed buildings or a national stock allocation. Results remain research-only; `runtime_promoted` is false.

## Contents

- `01_shared_engine/`: maintained physical, stock, scheduling, resource and reconciliation modules, their data/reference snapshots, and original regression files.
- `04_parallel_city_physical_tests/`: direct city-comparator dependency and synthetic test.
- `docs/THREE_COMPONENT_CONTRACT.md`: input/output contract, evidence boundaries and integration checklist.
- `docs/ARCHETYPE_INTEGRATION_RELEASE_V36.md`: source release notes.
- `docs/EXTERNAL_TESTING.md`: supported tests and optional source-bound checks.
- `provenance/source_manifest.json`: original/export file hashes and export adaptations.

Orava v_ex experiments, old research runners, historical ZIPs, large weather datasets, outputs and unrelated source archives are excluded. Public reference URLs are retained where available. Private cloud citations are replaced with bundled local references or opaque `export-reference:` identifiers; the latter are archival lineage labels, not downloads or execution dependencies.

## Model boundaries

The engine distinguishes buildings, dwellings and conditioned area; physical envelope, operation and heating devices; useful heat, final energy, delivered district heat and primary energy; and accounting success from empirical qualification. Conditional research openings and unresolved stock remain explicitly labelled. PAS/HDE priority-finance and protected-construction rules are preserved. Read the contract before supplying independent cases.

## Testing scope

The default command executes the portable cohort, archetype, surface, airflow, construction, weather-interface and synthetic city tests. It does **not** claim that every country/source regression is independently reproducible from this checkout. Run `python scripts/run_tests.py --extended` to also attempt extended modules whose declared optional prerequisites are present; unavailable modules are listed explicitly. No test is converted from failing to passing.

Please report the commit, Python/package versions, exact command, input boundary and failing assertion when reporting an issue. Keep any fresh blind observations separate from parameter development.

## Export status

This repository is a copy, not a change to the source model's governance or a new national release. Export changes are limited to standalone execution/documentation and source-reference portability. No new open-source license has been selected; existing authorship and third-party data rights are retained.
