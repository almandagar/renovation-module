"""Trajectory interface; the conserved cohort engine is the only active scheduler."""
from renovation_module import run

def compile_trajectories(input_path,output_dir):
    from renovation_pipeline import run_pipeline
    return run_pipeline(input_path,output_dir)
