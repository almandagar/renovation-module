"""Execute bundled synthetic acceptance or nine-donor component example offline."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / '01_shared_engine'
sys.path[:0] = [str(ENGINE), str(ROOT / '04_parallel_city_physical_tests')]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donors', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    from renovation_pipeline import run_pipeline
    if args.donors:
        import make_sk_donor_example
        bundle, donor_rows = make_sk_donor_example.build()
    else:
        from make_acceptance_fixture import fixture
        bundle = fixture()
    source = args.output_dir / 'inputs.json'
    source.write_text(json.dumps(bundle, indent=2) + '\n')
    print(run_pipeline(source, args.output_dir))
    if args.donors:
        from archetype_integration import prepare_bundle
        from archetype_physics import heat
        resolved = prepare_bundle(bundle)
        checks = []
        for cell, row in zip(resolved['opening_cells'], donor_rows):
            actual = heat(cell, resolved['library'], bundle['weather']['donor_comparison']['reference'])['h_w_k']
            if abs(actual - row[21]) >= 1e-8:
                raise AssertionError((cell['id'], actual, row[21]))
            checks.append({'id': cell['id'], 'actual_h_w_k': actual, 'reference_h_w_k': row[21]})
        (args.output_dir / 'donor_component_parity.json').write_text(json.dumps(checks, indent=2) + '\n')
        print('Nine donor component parity checks passed.')

if __name__ == '__main__':
    main()
