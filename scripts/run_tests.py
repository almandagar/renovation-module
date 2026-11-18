"""Run portable acceptance tests; optional source checks require explicit fixtures."""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / '01_shared_engine'
sys.path[:0] = [str(ENGINE), str(ROOT / '04_parallel_city_physical_tests')]
PORTABLE = [
    'test_archetype_integration', 'test_cohort_engine',
    'test_pas_newbuild_reallocation', 'test_pas_essential_timing_v35',
    'test_surface_state_integration', 'test_airflow_pressure',
    'test_airtightness_research', 'test_weather_living_exposure',
    'test_weather_urban_interfaces', 'test_city_physical_tests',
]
OPTIONAL = {
    'test_local_completion_evidence': ['file:SK_KE_V08_OBSERVED_COMPLETION_DECISIONS.json'],
    'test_panel_dated_delivery': ['module:sk_panel_dated_country_input'],
    'test_panel_event_scheduler': ['module:sk_kosice_panel_event_bridge'],
    'test_panel_floor_policy': ['module:sk_kosice_panel_event_bridge'],
    'test_panel_ra_physics': ['module:sk_kosice_panel_ra_country_input'],
    'test_renovation_geographic_reconciliation': ['module:sk_2021_heating_joint_source_bridge'],
    'test_sk_ke_site_identity_v09': ['file:SK_KE_V08_Observed_Decisions_SourceLedger.json'],
    'test_real_pecd_living_catalogue': ['pecd:weather catalogue'],
    'test_urbclim_city_exposure': ['module:rasterio'],
    'test_panel_spatial_integration': [],
}

def unavailable(requirement):
    kind, value = requirement.split(':', 1)
    if kind == 'module':
        return importlib.util.find_spec(value) is None
    if kind == 'file':
        return not (ENGINE / value).is_file()
    results = Path(os.environ.get('RENOVATION_PECD_RESULTS', ENGINE / 'external_fixtures/pecd_weather_catalogue/results'))
    return not all((results / f).is_file() for f in [
        'WS36_EU8_living_weather_exposure_metrics.csv',
        'WS36_EU8_living_weather_episodes.csv',
        'WS36_EU8_living_weather_qualification.json',
    ])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extended', action='store_true')
    args = parser.parse_args()
    modules = list(PORTABLE)
    omitted = {}
    for module, requirements in OPTIONAL.items():
        missing = [r for r in requirements if unavailable(r)]
        if args.extended and not missing:
            modules.append(module)
        else:
            omitted[module] = missing or ['optional suite not requested']
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    report = {
        'suite': 'extended-available' if args.extended else 'portable',
        'tests_run': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'skips': len(result.skipped),
        'modules': modules, 'optional_modules_not_run': omitted,
        'empirical_validation': False,
    }
    output = ROOT / 'outputs' / ('extended_test_results.json' if args.extended else 'test_results.json')
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
