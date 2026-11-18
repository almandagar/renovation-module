# External testing

Run `python scripts/run_tests.py` from the repository root. The runner sets the shared-engine and sibling city import paths explicitly. The numerical model is unchanged.

The source checkout's unrestricted unittest discovery also includes source-bound regressions whose independent datasets/adapters are absent. Before export, discovery ran 218 tests and reported nine dependency/fixture errors and 29 existing skips; that is not represented as a passing full suite. The seven contract acceptance modules alone passed all 145 tests. The portable runner additionally includes available weather-interface and synthetic city tests; see `provenance/test_results.json` for this checkout's exact result.

## Optional checks

`--extended` reports unavailable modules separately instead of claiming their source qualification. Source-bound requirements include:

| Test module | Additional prerequisite |
|---|---|
| test_local_completion_evidence | SK_KE_V08_OBSERVED_COMPLETION_DECISIONS.json |
| test_panel_dated_delivery | sk_panel_dated_country_input adapter |
| test_panel_event_scheduler / test_panel_floor_policy | sk_kosice_panel_event_bridge adapter |
| test_panel_ra_physics | sk_kosice_panel_ra_country_input adapter |
| test_renovation_geographic_reconciliation | sk_2021_heating_joint_source_bridge adapter |
| test_sk_ke_site_identity_v09 | SK_KE_V08_Observed_Decisions_SourceLedger.json and companion source files |
| test_real_pecd_living_catalogue | independent weather catalogue/source/model fixtures |
| test_urbclim_city_exposure | rasterio |

The PECD roots are configurable through RENOVATION_PECD_RESULTS, RENOVATION_PECD_RAW and RENOVATION_PECD_MODELS. No automatic network acquisition occurs. Installing optional dependencies does not provide the missing independent observations. Existing panel-spatial tests retain their own skip conditions.

## Independent evaluation

Declare geography, stock and weather year, occupancy, area denominator and energy stage before comparing observations. Separate AP/FH and carriers, unknown/retained coverage, adequate-service need and expected delivered energy. Software reconciliation and donor parity are not empirical accuracy. Do not use previously revealed outcomes as fresh blind targets.
