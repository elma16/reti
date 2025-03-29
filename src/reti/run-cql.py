import os
import subprocess
import argparse
from pathlib import Path

cql_path = Path("/Users/elliottmacneil/python/chess-stuff/reti/cql6-2/cql")


def run_cql_scripts(pgn_file, cql_folder, output_folder):
    """
    Runs CQL scripts against a PGN file.

    Args:
        pgn_file: Path to the PGN file.
        cql_folder: Path to the folder containing CQL scripts.
        output_folder: Path to the output folder.
    """
    if not os.path.exists(cql_folder):
        print(f"Error: CQL folder '{cql_folder}' does not exist.")
        return

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for filename in os.listdir(cql_folder):
        if filename.endswith(".cql"):
            cql_file = os.path.join(cql_folder, filename)
            output_file = os.path.join(output_folder, filename[:-4] + "_output.pgn")

            command = [
                f"{cql_path}",
                "-input",
                pgn_file,
                "-output",
                output_file,
                cql_file,
            ]

            print(f"Running CQL script: {cql_file}")
            try:
                subprocess.run(command, check=True)
                print(f"Output written to: {output_file}")
            except subprocess.CalledProcessError as e:
                print(f"Error running CQL script: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CQL scripts against a PGN file.")
    parser.add_argument("pgn_file", help="Path to the PGN file")
    parser.add_argument("cql_folder", help="Path to the folder containing CQL scripts")
    parser.add_argument("output_folder", help="Path to the output folder")
    args = parser.parse_args()

    run_cql_scripts(args.pgn_file, args.cql_folder, args.output_folder)
