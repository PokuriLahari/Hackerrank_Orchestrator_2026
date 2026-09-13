"""
Evaluation entry point for Buy or Wait? financial decision agent.
Invokes the main pipeline to generate output.csv and validate it.
"""
import os
import sys

# Add parent code directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import run_pipeline
from evaluation.validate_output import validate_output


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    dataset_dir = os.path.join(repo_root, "dataset")
    output_path = os.path.join(repo_root, "output.csv")

    print(f"Running evaluation from {__file__}...")
    run_pipeline(dataset_dir=dataset_dir, output_path=output_path, use_samples=False, verbose=True)
    validate_output(output_path, dataset_dir)


if __name__ == "__main__":
    main()
