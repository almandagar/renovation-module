# Renovation thermal and urban model qualification protocol V01

28 October 2026. Proposed prospective decision protocol, not completed testing or production authorisation.

## Decision and scope

Choose the least costly method that meets the accuracy required for each use: annual stock energy, intervention savings, hourly capacity/electricity, indoor service, neighbourhood exposure and urban adaptation. ISO 52016-1 is a calculation standard; pyBuildingEnergy is one implementation. They are not independent candidates. EnergyPlus is a detailed comparative implementation, not experimental ground truth. Urban-weather models supply boundary conditions and feedback; they do not replace the conserved stock ledger or automatically solve building physics.

Retain one national stock with sparse archetype × construction-period × component-condition × neighbourhood partitions. Construction period constrains original characteristics; current component states determine remaining interventions. New construction from 2011, demolition, conversion and renovation retain separate events. Dated energy and whole-life-carbon requirements remain in the construction/standards registry; solver selection cannot establish regulatory compliance by itself. Existing national PI/PAS/HDE outputs are unchanged during qualification.

## 1. Candidate register

| Candidate | Role | Qualification question |
|---|---|---|
| Current archetype_physics.heat, frozen revision | Existing annual/seasonal baseline | Is its aggregate accuracy adequate and transferable? It cannot itself qualify dynamic comfort or outages. |
| One physically constrained low-order RC model, frozen equations | Cheap dynamic alternative; choose one, not a proliferation | Can it capture storage, solar and power-limited service with fewer inputs/cost? |
| Pinned pyBuildingEnergy ISO 52016 implementation | Standards-based hourly candidate | Does its implementation and configured zoning reproduce observations and renovation response? |
| Pinned EnergyPlus, selected subset | Independent detailed numerical challenger | Do disagreements persist under matching geometry, boundaries and controls? |
| IWU source-native seasonal calculation | German source-method reproduction | How much of the national gap comes from equations, weather, service, area and stock? Not an independent observation. |

First use the existing pyBuildingEnergy V4/V9 commit. Any newer revision is a separate candidate with change log and replay; do not silently mix results. Verify actual installed capabilities and system/control APIs before promising a coupling. A model needing rich inputs must not gain an advantage from information denied to the others.

## 2. Freeze evidence before comparisons

Create a machine-readable case register: evidence ID, file hashes, building/room IDs, floor-area definitions, surface areas/orientations, adjacency and ground, material assemblies and uncertainty, windows/shading, air exchange, HVAC/emitter, gains, measured carriers/useful heat, DHW, controls, occupancy, weather/timezone, sensor interval and accuracy, missing-data mask, intervention dates, and calibration/validation membership. Record each field as observed, source-derived, inferred or scenario prior. Derived inference retains its method and uncertainty.

Check whether a source power value is an interval average or instantaneous sample and whether its timestamp denotes interval start/end. Verify time offsets with independent metadata and solar observations, not target-fit optimisation. Preserve leap-day and daylight-saving transformations explicitly. Do not use TMY filler during scored historical periods; verify initial thermal-state convergence with measured antecedent weather.

Use two tracks: (A) no outcome fitting, independently specified physical inputs; (B) bounded calibration using the same early data and an explicit parameter budget for all eligible candidates. Report both. A source-derived model and a calibrated model answer different questions. Do not penalise non-identifiable parameters by forcing a spurious point estimate.

V08/V09 have already exposed the later N2 observations. They are development data now, not fresh blind evidence. Freeze the next configurations before unlocking a genuinely unused interval, experiment or building. If no fresh evidence is available, label the result development-only; execution can continue without claiming external validation.

## 3. Gate A — implementation and adapter qualification

Run applicable analytical and standard benchmark cases. Record the exact standard edition, weather and normative acceptance data. Missing licensed reference values mean ungraded, not pass. Check steady transmission; adiabatic and party-wall limits; equilibrium; zero heating/cooling; positive storage; solar orientation/shading; ventilation and heat recovery; ground treatment; timestep and warm-up convergence. Check units, signs, useful versus final energy and conservation at each interface.

For controls, supplied thermal output must feed back into air/fabric state. Test capacity saturation, heating interruption, recovery, comfort rebound and zero-power free float. COP division after an ideal-load simulation is not a capacity-limited test. Preserve software tests separately from empirical accuracy tests.

Gate fails for unexplained unit/energy imbalance, wrong time alignment, silently substituted inputs or unsupported required outputs. A candidate may remain eligible for annual energy while ineligible for comfort or system adequacy.

## 4. Gate B — immediate Twin Houses experiment

Reconstruct N2 using existing constructions, plans, glazing, external shading, room/channel schedules and directional radiation documents. Extract actual room areas, orientations, conditioned volume, ground/basement boundaries and operating air exchange. Measured coheating HTC is a separate regime-specific check; do not force the operational model to equal it. Use the current geometry-prior reconstruction as a sensitivity case, not the reference building. Test whether a qualified equivalent zone suffices; add multiple zones when room exposure/control makes aggregation materially inaccurate.

Execute three distinct experiments:

1. **Measured heat → temperature.** Feed measured sensible heater output and IHS gains, actual weather and observed operation into the dynamic candidates. Predict zone air temperatures, unheated temperature decay and recovery; compare operative temperature only where measured or defensibly derived. This isolates fabric/storage/solar from thermostat imitation. The current steady heat function is not eligible for this endpoint; include persistence/control and a fitted simple predictor as skill baselines.
2. **Documented control → heat and temperature.** Reproduce room thermostats, emitter limits and schedules. Predict delivered heat and indoor air together. Disclose unobserved control details and bracket them; do not silently replace them with constant 20.5°C operative control. Score hourly and daily heat, whole-period energy, cold/night and sunny/day errors, peaks and comfort shortfalls.
3. **Controlled ablations.** Compare independently verified solar geometry/shading versus the prior, measured versus bounded air exchange, source ground versus equivalent-U, single versus multiple zones, and fixed versus observed gains. Change one factor at a time for attribution, then test consequential interactions. The V9 g=.10 result is a post-hoc development diagnostic, not an accepted glazing property.

Use block-held-out periods including sunny/cold, overcast/cold and recovery conditions; withhold complete experiments/buildings where feasible. N2/O5 are not before/after renovation. Admit O5 as useful-heat validation only after whole-system delivered hydronic heat is established; compressor electricity requires separately qualified equipment/system accounting. Keep weather, masks, geometry and service identical across candidates except deliberately tested differences.

## 5. Gate C — renovation response and sparse-input usefulness

Retain the four Paris measured climate-adjusted five-use observations as a development structural challenge. Reconstruct documented actual intervention packages, pre/post components, heating/DHW systems, occupancies, floor areas and normalisation. Useful space heat, carrier energy and five-use totals remain separate observation operators. Do not convert all savings to fabric or use an arbitrary non-heating residual to force a fit.

For site-qualified cases, predict both pre and post levels and the change, including comfort take-back and equipment changes. Report percentage-point savings error and absolute kWh/m² error; a correct percentage can conceal two wrong levels. Add independent held-out retrofit buildings or programmes when available. At least one independent intervention group beyond a single site is required to claim transfer; the sample size must ultimately reflect observed between-building variability, not hourly row count. No complete renovation history is required: bounded present-state reconstruction and documented tested interventions suffice.

Run a data-ablation track: rich as-built; realistic archetype/period/component-state inputs; sparse stock inputs with bounded latent condition distributions. Hide the same fields from all models. Compare accuracy, uncertainty coverage, input labour and run cost. Never fill hidden inputs from validation outcomes. Transfer to a distinct archetype/climate only where evidence exists; unsupported hospitals, social housing, Orava cubes and warm-climate stock remain explicit applicability gaps, not reasons to halt all useful modelling.

## 6. Gate D — urban weather as a separate factorial test

Start with one city that has usable coincident rural/background and urban air measurements and morphology. Select by evidence, not prestige or convenience; Berlin, Paris and a Slovak city are candidates, not admitted datasets. Begin with dense/attached, open residential and vegetated forms plus a defensible background reference. Qualify station height/siting, elevation, exposure and representativeness. Hold out stations/neighbourhoods and an entire heat episode where possible.

Weather treatments: W0 qualified background; W1 simple empirical hourly urban correction trained on separate evidence; W2 UWG morphology-driven output; W3 accessible UrbClim field with compatible forcing. Observed local urban weather is the reference forcing for isolating building-model error, not a model candidate. Do not sequentially stack UWG on an already urban UrbClim field without a defined residual correction.

First score urban air temperature, especially night bias, event amplitude/timing, wind and humidity where produced, against observations. Then cross eligible W treatments with two leading building solvers on identical stock/operation. Compute weather effect, solver effect and their interaction; a better building prediction cannot conceal a worse local-weather prediction. Use background and urban observations from the same period; historical local weather validates the method, while future PECD cases are conditional stress projections.

Factor physical interventions separately: (i) canopy-air conditions; (ii) facade solar/shading and longwave; (iii) ventilation exposure; (iv) vegetation/water availability; (v) equipment heat rejection. Do not add a tree's shading benefit twice through weather and building geometry. Match reference heights; pedestrian mean radiant temperature is not an EPW air temperature or an automatic facade boundary.

UWG is the practical low-cost contender, not the presumed winner. UrbClim is a spatial challenger, not observed truth. SOLWEIG serves outdoor radiation/shade and pedestrian comfort; it is not a UHI air-temperature substitute. Use PALM-4U or WRF-BEP/BEM only where consequential residuals, terrain/circulation or heat feedback justify process resolution. Detailed-model agreement is corroboration, not independent field validation. Check access, licence, executable availability and inputs before scheduling these models.

If testing cooling feedback, avoid double-counting UWG's internal building heat rejection and the external building solver's rejection. Define which owns that flux; check heat/energy accounting, location and timing. In cooling, rejected heat includes removed indoor heat plus equipment input. Winter heat-pump effects require a signed physical balance, not a fixed warming factor. Start with one-way coupling; add iteration only if sensitivity shows it materially affects the decision and convergence can be demonstrated.

## 7. Gate E — weather ensemble and national conservation

Use cheap screening for all 36 PECD members, then run leading thermal candidates across all 36 for a small archetype-condition panel. This is much cheaper than the complete national coupled model. Include ordinary cases as well as extremes and report results by climate-model family; do not treat 36 scenario-years as independent equally likely observations.

Select reduced full-year members from building-response metrics and electricity stress jointly, preserving synchronous countries/variables. Retain separate scientific purposes and constraints in the selection objective. Test 8/10/12/13 options against the complete-panel results. Add WS17 and other event windows where useful. For each window, extend antecedent and recovery until key results converge relative to the complete-year run. Preserve actual cross-year source continuity when available; never join different families or unrelated years to invent it. Partial-year tests cannot establish annual energy accuracy.

Repeat the final reduced/full comparison on at least one qualified coupled energy-system configuration. Check annual energy, hourly and multi-day peaks, shortage duration/magnitude/timing and strategy order; an extreme-biased subset yields conditional stress outcomes, not probability-weighted EENS.

Independently test that a city partition replaces, rather than adds to, its national parent. All candidate solvers use identical stock weights, conditioned-area boundaries and intervention events. Renovation changes state, not stock quantity; newbuild, conversion and demolition remain distinct. Repeated light interventions update components without counting savings twice. Cumulative deep-renovation assessment uses a stable, defensible reference and fixed service, alongside actual-use outcomes. Do not alter PAS/HDE finance exclusions or delivery/diffusion rules through thermal calibration.

## 8. Scoring, statistical design and proposed practical tolerances

Publish paired differences by building/episode, not pooled hourly scores alone. Use block lengths informed by residual autocorrelation; show 1/3/7-day sensitivity and resample buildings when multiple buildings exist. Thirty-two days in one house are not 32 independent buildings. Preserve untouched evaluation data and publish all registered candidate results. Failed runs count as reliability evidence, not silently dropped cases.

Proposed engineering targets below are decision tolerances to freeze before fresh validation, NOT ISO/ASHRAE acceptance limits or claimed health thresholds. Tighten/relax only with a documented reason before unlocking outcomes. Sensor and boundary uncertainty can make a verdict inconclusive.

| Endpoint | Initial target and safeguard |
|---|---|
| Period/annual useful heat | absolute bias <=10%; monthly/seasonal breakdown and daily error must also be acceptable; low-load cases use absolute kWh thresholds set from metering uncertainty |
| Indoor measured air response | MAE <=1°C and absolute night bias <=0.5°C; report worst rooms, 95th-percentile error and time below/above declared service thresholds |
| Delivered heating peaks | <=15% error in defined hourly and sustained peak metrics, plus event timing; observation resolution must support the claim |
| Retrofit savings | <=5 percentage-point error as an initial target, alongside pre/post absolute levels and uncertainty; provisional where components/end uses are unresolved |
| Urban air weather | night mean bias <=0.5°C, MAE <=1°C, plus event amplitude/timing; assess held-out stations and weather episodes |
| Reduced ensemble | <=5% deviation on panel annual-energy summaries and <=10% on defined peak/duration measures; no loss of a declared decision-changing stress event; near-zero outcomes need absolute tolerances |

A more complex candidate earns main-engine adoption when it meets relevant absolute targets, gives a predeclared practically meaningful improvement (initially 10% in the primary paired error metric) on fresh evidence, and avoids material degradation in the other essential endpoints. Confidence intervals and measurement uncertainty must support the claim; otherwise retain an equivalence/inconclusive outcome. Error targets are not permission to disregard a consequential threshold crossing.

If two candidates are equivalent for annual heat but only one predicts capacity/comfort adequately, route tasks accordingly. If site-rich improvement disappears in sparse archetype inputs, retain the detailed model as a reference/validator or derive a separately validated reduced surrogate. Runtime, memory, input preparation labour, failure rate, licensing and maintainability are reported alongside accuracy. Calibrated interval coverage should be assessed; a very wide interval that contains everything is not useful precision.

## 9. Deliverables and order of execution

Keep the work in the existing shared-engine/test/output structure. Use one protocol and a machine-readable case/holdout register, adapters for candidate solvers, immutable observation masks, per-case scored traces, uncertainty and attribution tables, and one decision record per endpoint. Do not create another national stock engine or make a ZIP the primary output.

First pass: fix V8/V9 vacuous holdout and hash checks; bind all files to real source hashes; reconstruct N2 solar/zones/controls; rerun development diagnostics; freeze inputs and select fresh validation. Second: measured-heat temperature test and controlled-demand test. Third: qualify actual retrofit response and sparse-input transfer. In parallel, audit one city dataset and test empirical correction versus UWG. Fourth: 36-member panel, reduced ensemble, equipment/system coupling and conservation checks. Escalate to detailed city modelling only on demonstrated need.

Possible decisions: keep shared annual solver; use validated RC for hourly stock; adopt pyBuildingEnergy for qualified classes; retain EnergyPlus as detailed challenger; add validated urban conditioning only for suitable neighbourhood classes; or retain all methods as research if evidence is insufficient. A conditional hybrid is a valid outcome. No winner is predetermined.

## Sources and supporting evidence

- V08 measured-building work: export-reference:6dc46815f31eb74c
- V09 actual shared/ISO comparison: export-reference:cd4391b8ab4cc19b
- PECD catalogue methodology: export-reference:6ed02b4764841439
- pyBuildingEnergy source and implementation scope: https://github.com/EURAC-EEBgroup/pyBuildingEnergy
- EnergyPlus analytical/comparative testing: https://energyplus.readthedocs.io/en/v23.2.0/tips_and_tricks/tips_and_tricks.html ; https://energyplus.net/testing
- UWG developer documentation: https://www.ladybug.tools/uwg/docs/ ; https://github.com/ladybug-tools/uwg
- UrbClim developer description: https://climasys.vito.be/en/services/model ; https://urban-climate.be/model
- PALM-4U building/atmosphere coupling, original research: https://gmd.copernicus.org/articles/14/3511/2021/
- SOLWEIG reference manual: https://umep-docs.readthedocs.io/en/latest/OtherManuals/SOLWEIG.html

The attached proposal informed the candidate list. Its preferred models and 8–12-member target are hypotheses to test, not conclusions adopted in advance. Current web documentation can describe capabilities beyond the pinned V4 revision; pin and verify the executable before use. All numerical acceptance targets and run ordering above are this protocol's proposed design choices.
