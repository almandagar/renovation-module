# Integration update — cohort-state v3.1, 26 October 2026

The main input schema is now `building-stock/2`; optional `stock_validation` still uses this diagnostic interface. Earlier aggregate-run test counts below apply to the previous engine only. The replacement's 40 tests are separately documented in [the current contract](export-reference:72f2187bf24542c7). Detailed local tests use the [current city-v2 module](export-reference:7acc3ce4f9549fb1) and [exact-cell snapshot adapter](export-reference:5f3a2e444ca8490b). Independent observations are not replaced by the acceptance fixture.

---

# Shared stock-validation engine — 26 October 2026

The renovation application has three production components and one distinct validation engine. Validation diagnoses inputs and results; it does not fit the stock automatically, infer hidden renovation, change strategies, or promote EN/PF/TT forecasts.

## Run and inputs

The main builder accepts an optional `stock_validation` block in a `renovation/1` country bundle. It always writes validation outputs: absent checkpoint inputs are reported OPEN_NO_CHECKPOINTS. Existing trajectory-only compatibility calls remain trajectory-only.

Standalone diagnostic use:

```sh
python renovation_validation.py --country Netherlands --inputs ../02_country_inputs/nl_gas_validation_source_adapter.json --output-dir ../03_outputs/nl_validation
```

`stock-validation/1` config contains `checkpoints`, optional `cohort_outcome_checks`, optional `gas_attribution_checks`. Each checkpoint defines `boundary`, `observation_boundary`, weather, physical cohorts, observed carriers, declared test role and source families. The DEMO JSON gives the full machine-readable example; it is synthetic, not a French national validation.

All energies are TWh except the reused French cohort adapter, whose explicitly named kWh fields retain their original units. Final carrier observations must be converted to LHV/PCI before ingestion. Useful heat and HP ambient heat remain separate from final energy. No automatic PCI/PCS conversion is guessed.

Boundary agreement is required across country/year, geography, population, service, energy stage, weather basis, energy basis and timing basis. A mismatch retains diagnostics but blocks a numerical carrier residual. Predictions are annual calendar-exposure inputs, not end-year stock multiplied as if it operated all year. Cohort `area_m2` must represent annual mean conditioned exposure; `installed_year` identifies equipment vintage and does not prorate exposure. Future equipment is rejected. The engine does not yet automatically translate the dated replay into intra-year cohort exposures. That is a remaining adapter task, not an assumed completed integration.

## Physical stock and service

Each uniquely identified cohort has EXISTING or NEW_BUILD origin, conditioned m², standard useful kWh/m² under the declared reference climate, service factor, heated fraction, optional energy-poverty service factor and heating-system useful-heat shares. Existing/newbuild space-heat accounts are reported separately and together. Nonheating consumption, when supplied, is kept outside those space-heat origin subtotals.

Central values and low/high input bounds are explicit. Uncertain bounds require an evidence reference. Joint extrema are scenario bounds, not confidence intervals. Service and poverty factors must be constructed to avoid overlapping the same reduction; no coefficient is estimated here. Missing poverty evidence can remain an explicit prior, but does not justify a national underheating estimate. Factors do not alter fabric intensity. Stock-area residuals compare supplied observed conditioned area with modelled coverage.

Indoor-temperature observations are tested against a declared comfort temperature. This is a range/compatibility diagnostic; temperature measurements do not automatically identify U-values or prove a renovation. Heating schedules, room coverage, gains and poverty can remain alternative explanations. There is no claimed dynamic indoor-temperature solver or heating-capacity model.

## Weather and climate

Actual-weather space heat uses actual/reference HDD against the reference-climate intensity. A separate physical run uses reference HDD and explicitly supplied reference SPF. Both weather source and reference period/base temperature must be declared. Optional daily mean temperatures must cover the complete checkpoint calendar year and reproduce supplied HDD. This is a linear HDD screening model; not a monthly thermal balance or a temperature-dependent COP solver. Reference-climate physical predictions do not automatically climate-normalise measured household totals. Solar/wind gains, cooling, humidity and overheating are not modelled by this first version.

## Equipment and carriers

Reused heating-stock accounting handles HP electricity, ambient heat and optional gas backup; explicit actual/reference SPF can vary by vintage/cohort. Unit inventories reconcile opening + commissioning − retirement to observed closing. Sales must first be translated into commissioned operating units with evidence; sales are not automatically installations.

Gas, electricity, district heat, bioenergy, oil, coal and other carriers are compared separately. Observed values may be bounded or missing. Missing bioenergy is null, not zero. Total final-energy comparison is computed only when every carrier is explicitly supplied (including known zeros) and boundaries match. Exported generation is not consumed electricity. Meter reconstruction uses gross imports plus onsite self-consumption minus annual storage inventory increase; net-import data are rejected without reconstruction. Source definitions must ensure battery losses and onsite self-consumption are not counted twice.

ALL_HOUSEHOLD tests require explicit complete nonheating coverage; SPACE_HEAT excludes other uses. Gas cooking/DHW and nonheating electricity cannot be silently interpreted as heating. District heat is delivered heat, not plant fuel.

## Social overlay and independence

Physical predictions remain unadjusted in the report. A Social overlay requires an exactly matching boundary, evidence reference and carrier factors. It produces separate adjusted predictions. Declared already-embedded adjustments are rejected. Calibration parameters are not modified. HOLDOUT is called held out only with explicit independence review and distinct source family; same lineage is flagged. A declaration is not an automated audit of source independence.

Reused French cohort functions preserve the prohibition on a second price correction to an empirical realised treatment effect. The Dutch gas adapter reproduces mix, within-state and unallocated components without assigning causal renovation effects. National source ingestion and causal household price coefficients remain with their owners.

## Outputs, tests and readiness

`validation/stock_validation.json` preserves predictions, observation bounds, residuals, coverage, stock origins, equipment and comfort checks, test-role/source-lineage status, cohort outcomes and gas attribution. `checkpoint_dashboard.csv` provides one row per checkpoint/carrier. Main run manifest links both files. Unexplained residuals remain unexplained; no overall national certification is issued.

136 software tests executed: 135 passed, one inherited optional test skipped. This includes 23 new validation checks and existing stock/trajectory, heating-accounting and French cohort checks. The heating-source fixture is retained for the inherited source checks. A synthetic French country bundle exercises the main entry point. The source-derived Dutch 2022–2024 same-method decomposition is reproduced separately; it is not a full Dutch thermal-stock validation.

Next numerical work: map qualified national calendar-year cohort exposures and matched all-carrier observations; extend/check comfort and poverty distributions; supply vintage/weather-specific SPF; reserve withheld years/regions; then diagnose residuals across checkpoints. Extend temperature physics only when evidence warrants it. Existing national forecasts remain unchanged.

## Owners and methodology references

- [Building stock/history owner](export-reference:8e85d08c7710f52c)
- [Social household-response overlay](export-reference:b6dd11b8d126087c)
- [Heating bridge source package](export-reference:17319220356f3f0a)
- [French cohort source package](export-reference:b60ab11aec1aba06)
- [Dutch attribution source package](export-reference:15a25e2e260e5cb8)
- [ODYSSEE climate-correction methodology](https://www.odyssee-mure.eu/faq/energy-efficiency-methodology/)


## Parallel city physical testing — 26 October 2026

The detailed local energy–comfort solver is a separate [parallel city test module](export-reference:296c377ae5449ac0), documented [here](export-reference:ed3509476c199225). It is not imported or run by the shared renovation/stock-validation engine. It consumes an explicitly versioned national prediction snapshot and local evidence; it hashes the snapshot and reports feasible physical/service hypotheses, inconsistencies and unresolved alternatives. There is no automatic national parameter update. A supported revision goes through reconciliation with an explicit transfer scope and new independent testing where available.

The first implementation is a quasi-steady period heat-balance screen using geometry/U-values, ventilation, adjacent spaces, indoor/outdoor temperatures and usable gains. It is not a dynamic temperature or peak-capacity solver. Nine software tests pass; supplied examples are synthetic, not city calibration. Complete renovation histories are not required. Qualified spatial partitions can be admitted through their own identity and conservation checks. Existing shared runtime files and forecasts are unchanged by this separation.


