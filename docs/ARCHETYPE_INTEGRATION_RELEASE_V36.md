# Archetype integration release v3.6 — 12 November 2026

Published in the existing shared-engine folder, retaining canonical module, pipeline and contract IDs. Adds `archetype_integration.py`, targeted regressions, a frozen source snapshot and an executable Slovak FH donor example. Shared and Slovak FH/AP workbook guidance now permits qualified conditional research instead of blanket exclusions.

## What is executable

- Explicit compatible fallback selection resolves real physical library profiles and preserves quantities, component state and heating.
- A country-neutral dated research opening avoids fabricated pre-2011 history and historical first-deep credit.
- Every normal pipeline run emits `archetype_integration_checklist.json`, including source review, physical inputs, independent stock controls, uncertainty, output-specific limits and quantitative opening coverage.
- Physical, accounting and empirical claims remain separate. Missing resource data does not stop valid heat research; it does prevent claims of demonstrated resource-constrained delivery.

## Verification

137 targeted software checks pass (19 new, 118 inherited). Nine source-derived square/cube/Orava form-state profiles execute through the shared pipeline, and all nine component H coefficients match workbook values within 1e-8 W/K. Example checklist: EXECUTED_CONDITIONAL, 9 hypothetical buildings / 9 hypothetical dwellings / 1,558.32 conditional m², all selected through physical fallback rules. These quantities describe an interface example, not Slovak stock.

Run `python make_sk_donor_example.py` from the engine directory. The bundle includes its exact input, frozen donor rows, machine checklist, resolved inputs, outputs and component-parity record. The zero-gain HDD screen is deliberately different from workbook net-loss-factor heat estimates; no U-values were fitted to intensities. No work-hour or material inventories were fabricated.

Regression command from the engine directory, using the bundled supporting city module:

```sh
PYTHONPATH=../04_parallel_city_physical_tests python -m unittest -q test_archetype_integration test_cohort_engine test_pas_newbuild_reallocation test_pas_essential_timing_v35 test_surface_state_integration test_airflow_pressure test_airtightness_research
```

## Workbook corrections and limits

- Shared: replaced blanket profile/as-built/history exclusions with conditional or output-specific statuses; updated adapter chronology and version guidance; added visible Engine_Intake_Contract.
- Slovak FH: made component-donor use explicit and distinguished aggregate POSTWAR_A 189/120/62 proxies from physical solver inputs. Added visible contract tab. Numerical inputs and formulas retained.
- Slovak AP: clarified conditional admission of historical discrete-family fallbacks. Historical flat weights remain historical flat weights. Martin geometry and Košice thermal screens are not current national observations. Added visible contract tab; no national share or physical parameter was invented.
- Original reconciliation release V03 confirms that earlier Martin parse errors had already been repaired and that AP V16 provides a constrained conditional central below the all-AP ceiling. V14 remains an invalid historical diagnostic; these were not newly repaired in this release. The underlying central remains inferred rather than independently observed.

This is a targeted intake/gate review, not a cell-by-cell audit of every workbook tab. The apartment fallback is admitted by the generic executable interface but this release does not supply or validate a complete national AP allocation. Country adapters must select compatible physical branches, reconcile stock quantities and execute the resulting national scenarios. A list of donors alone remains insufficient. Workbook layout was checked through native formatting/structure readback, not a full rendered visual inspection.

## Supersession and publication evidence

Full pre-change raw archive: export-reference:b3a2a4008725c45b

Archive SHA256: `39f01601754c77bc389f159be19a451587c5f5684fc30e6ed6e7a04700fa6225`. Remote bytes verified against local archive. It contains 159 original raw files. Full native workbook copies were also preserved before modification:

- Shared: export-reference:88c814788e366910
- FH: export-reference:6060a9c909932e7e
- AP: export-reference:e19b64458c4d53a1

Published module, pipeline, contract and new intake module were downloaded and SHA256-checked against the tested local files. Methodology clarification readback was verified in model_basics, model_spatial, model_renovation_principles, model_essential_housing and model_renovation_engine.

## Current entry points

- Contract: export-reference:72f2187bf24542c7
- Shared workbook: export-reference:5d891e4685f0ff2b
- FH workbook: data/sk_fh_donor_snapshot_v36.json
- AP workbook: export-reference:2a40cec4bc52e23e
- Original release V03: export-reference:381a8336306d7ae7

No national forecast, empirical accuracy certification or EN/PF/TT promotion is claimed. Existing essential-construction protections remain active; no location optimiser, migration module or universal ±10% threshold was added.

## In-place verification correction

Updated 12 November 2026 without supersession as requested. 145 targeted regressions now pass. Direct and fallback profiles receive consistent declared-scope checks. Machine output separately reports execution, integration completeness for the requested output scope, physical coverage, assignment evidence and empirical qualification. A versioned source-scope manifest detects omitted declared families and incompatible review metadata. Navigation now points to v3.6 and the workbook intake tabs.

The added panel-mixture acceptance regression checks separate component calculations, disjoint quantity conservation, area-weighted intensity, a visible unresolved branch and a simpler fallback comparison. Only the 1999 flat counts are historical; its component profiles and area/building conversions are explicitly synthetic. A source-qualified national apartment-building application remains outstanding. The regenerated FH example correctly reports successful execution but incomplete source-scope integration rather than silently claiming complete review.
