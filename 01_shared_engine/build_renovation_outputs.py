import argparse
from renovation_pipeline import run_pipeline
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--country-inputs',required=True);p.add_argument('--output-dir',required=True)
    a=p.parse_args();run_pipeline(a.country_inputs,a.output_dir)
