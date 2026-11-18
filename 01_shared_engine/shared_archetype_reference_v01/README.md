# Shared renovation archetype reference package v01


18 October 2026. Source-stage, executable reference package; no national PAS/HDE delivery or EN/PF/TT/hourly runtime promotion.



## Live owner and package use

[The common archetype library](export-reference:02831c06f563c49c) supplies the live registry, physical definitions, specialist companions and validation. Start with the [master README](export-reference:cff4857562ca6544) and [v3.6 intake](export-reference:5d891e4685f0ff2b).

This directory holds the October source reference and engine-side files. Reproduce the maintained engine from the [v3.6 release ZIP](export-reference:190e5a5efd843bd9). The [18 October patch](export-reference:2eaa923101a4a039) is a historical snapshot. The loose JSON, CSV and fixture names remain available for consumers. The test-only physical library and standards seed are fixtures or source-stage seeds.

The [steel proxy workbook](export-reference:c7b004be77c22951) is the editable source for the four October steel CSV mirrors. This source publication does not establish material quantities for a country. The [PAS seed](export-reference:cda0fee83a3e2411) follows the [functional-community design owner](export-reference:dc280a75f9579d7d) for its service and spatial boundary.

## What is included


- 54 source-native German IWU2025 residential archetypes and 162 PI-reference packages (partial / medium / source-labelled deep).
- 26 physical project/cohort records, 95 source-native observation rows, 20 donor-mechanism links, and 72 strategy definitions across eight countries.
- 12 residential/public-service reference slots preserved from the source. Open slots do not acquire invented post-performance or housing quantities.
- A matched modifier engine, a reproducible builder and validation tests. The 10% material / 8% time / 9% residual-energy example is synthetic and rejected by default as an empirical input.


## Evidence and interpretation


The maintained source is RENOVATION_PATHWAY_DIFFUSION_PIPELINES_V02:
export-reference:9d4204af09991180
Source modified: 2026-10-18T20:32:37.192Z. Exact source section index and data-row references are retained. These are text-export coordinates, not guessed Google Sheets tab coordinates. Primary project URLs, units, reported stages and caveats are preserved. Original research wording is archival and is interpreted under the current package rules.


The archetype baseline heat and geometry are synthetic IWU model averages, not audited occupied/heated stock. Post-renovation reference intensities are EXPLICIT SCENARIO PRIORS formed from the existing PI depth saving fractions, not measured archetype-specific project results. Material depth indices are relative priors, not kg/m²; time=100 is a normalised index, not days or person-hours. Source-labelled PI 'deep' does not establish PAS-DEEP >=60% qualification. Do not aggregate these reference intensities into national TWh without a compatible deployment/stock account.


Project IDs with known aliases are consolidated, while raw source IDs remain traceable. Multiple observations and references are not additional physical projects. Completed, planned, experimental, LCA-modelled and implementation-stage results remain distinct. Net-PV balance, primary energy, final energy and useful heat are not interchangeable. Carbon factors are not material-mass factors. Donor observations are not automatically recipient-country coefficients.


## Agreed pathway rules


Finance is excluded from PAS and HDE renovation assessment: NOT_APPLICABLE_PRIORITY_PROJECT. It cannot affect feasibility, activity, adoption, central/low/high delivery, certainty or timing. No budget, credit, grant, payback or investment-economics test applies. Financial observations remain archival only. PI retains its own finance assessment.


Use a shared country/archetype/intervention reference, not the PI national pathway. PAS/HDE independently determine priorities, eligible intervention windows, package mix, adoption and deployment timing. Their physical constraints are qualified labour, humane working time, project preparation, resident-safe coordination, procurement execution, QA, safety, resource/environmental limits and consequential product capacity. Missing detail permits labelled priors and sensitivity; wrong physical semantics block the affected calculation.


Strategy alternatives, capability timing (early/central/delayed), delivery quantities (low/central/high), and performance envelopes are separate dimensions. PAS retention/adaptive must meet common service/energy/carbon requirements, not reproduce PAS-DEEP counts. Heating conversion, DHW, cooling, IAQ, retained/removed/reused materials, avoided newbuild, demolition and additions need their own accounts. Construction feedback is lagged.


## Matched modifiers


For the same archetype, intervention scope and service boundary:
- Alternative installed material = reference installed material × material factor.
- Alternative execution time = reference time × time factor, preserving stage and calendar-versus-person-hours semantics.
- Residual-demand factor: post demand × factor.
- Savings factor: pre demand − (pre demand − reference post demand) × factor.
- Additional percentage points: reference post demand − pre demand × points/100.


For pre=100 and PI post=40, 9% lower residual demand gives 36.4; 9% greater savings gives 34.6; nine extra percentage points gives 31. At 30% uptake of a matched 10%-lower-material package, activity-weighted material factor is 0.97 before changes in total activity/mix. Eight percent shorter time gives a theoretical 8.70% capacity increase ONLY if the affected resource actually binds and other requirements are unchanged; it is not an automatic national uplift.


The StepUP 2.72/3.56 comparison is retained only as a source-specific onsite person-hour/facade-area comparison. It is not a full-project time or German national productivity multiplier. Other modifier candidates retain null numeric factors until a compatible judgement or explicitly governed prior is recorded. No new dataset joins are mandated.


## Use


From the module directory:


    python build_reference_package.py --source source_snapshot/pipeline_text_export.txt --source-modified 2026-10-18T20:32:37.192Z
    python build_renovation_outputs.py
    python -m unittest discover -s tests -p 'test_renovation*.py' -v


The default build now validates and exports the shared references alongside the corrected PI output. PAS/HDE national delivery remains unpromoted: the next step is a country/archetype deployment adapter consuming these references, not another project-discovery programme.


## Steel material-intensity proxy layer — 25 October 2026


Steel is now represented as a separate CONSTRUCTION_BOM support layer rather than being embedded in thermal-archetype or renovation-depth indices. The package includes `steel_material_intensity_proxies_v01` plus CSV mirrors for the proxy library, archetype crosswalk, intervention rules and source notes. COMMON_BUILDING_ARCHETYPES remains the system/archetype owner, RENOVATION owns intervention events, and CONSTRUCTION_BOM remains the sole numeric owner of material quantities.


The layer separates existing stock steel, newly installed steel, removed steel, recovered steel and recycling/reuse routes. Missing drawings or BoQs never imply zero. Component lower bounds (for example B70 longitudinal rebar) are not whole-building intensities, and kg/m² floor area, kg/m² NFA, kg/m³ built volume, kg/panel and t/building are not converted without an explicit denominator bridge.


For CEE masonry single-family forms, including square/cube/Orava/Type-V, selected RASMI v20230905 EU12 masonry-SF p25/p50/p75 steel ranges are available only as flagged sensitivity envelopes. The relevant EU12-H/M rows have zero raw regional observations and are incremented from a wider pool, so they are not authoritative archetype quantities. Orava retains direct evidence of a steel/Hurdis ceiling but no invented whole-building steel mass. For T06B/B70, source-native demolition/component evidence retains priority, with RASMI RC-MFH ranges as broad controls. For WBS70, the EU15 RC-MFH range is a stronger broad regional/function/structure control but is still not a WBS70-specific BOM.


No proxy is promoted to runtime or national tonnes by default. Promotion requires a compatible archetype/system match, denominator closure, stock ownership and CONSTRUCTION_BOM adoption; intervention additions and demolition/recovery flows remain separate.