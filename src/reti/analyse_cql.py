import argparse
import subprocess
import os
import re
import tempfile
import shutil
from pathlib import Path

def count_games_in_pgn(pgn_file_path):
    """
    Counts the number of games in a PGN file by counting '[Event ' tags.
    Handles potential encoding issues.

    Args:
        pgn_file_path: Path to the PGN file.

    Returns:
        The number of games found, or 0 if the file is empty or cannot be read.
    """
    try:
        with open(pgn_file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            # A common way to count games is by looking for the '[Event ' tag
            # Adjust this regex if your PGNs mark games differently
            matches = re.findall(r"\[Event ", content)
            return len(matches)
    except FileNotFoundError:
        print(f"Error: PGN file not found for counting: {pgn_file_path}")
        return 0
    except Exception as e:
        print(f"Error reading PGN file {pgn_file_path}: {e}")
        return 0

def find_cql_scripts(scripts_location):
    """
    Finds all .cql files in a given location (file or directory).

    Args:
        scripts_location: Path to a .cql file or a directory containing .cql files.

    Returns:
        A list of paths to .cql files.
    """
    cql_files = []
    path = Path(scripts_location)
    if path.is_file() and path.suffix.lower() == '.cql':
        cql_files.append(path)
    elif path.is_dir():
        for item in path.iterdir():
            if item.is_file() and item.suffix.lower() == '.cql':
                cql_files.append(item)
    else:
        print(f"Error: '{scripts_location}' is not a valid .cql file or directory.")
    return cql_files

def run_cql_analysis(pgn_file, cql_binary, cql_scripts, output_dir):
    """
    Runs CQL scripts against a PGN file and collects game counts.

    Args:
        pgn_file: Path to the input PGN database.
        cql_binary: Path to the CQL executable.
        cql_scripts: A list of paths to CQL script files.
        output_dir: Directory to store temporary output PGNs.

    Returns:
        A dictionary mapping script names to the number of games matched.
    """
    results = {}
    cql_bin_path = Path(cql_binary)
    if not cql_bin_path.is_file():
        print(f"Error: CQL binary not found at '{cql_binary}'")
        return None

    input_pgn_path = Path(pgn_file)
    if not input_pgn_path.is_file():
        print(f"Error: Input PGN file not found at '{pgn_file}'")
        return None

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True) # Ensure output dir exists

    print(f"Using CQL binary: {cql_bin_path}")
    print(f"Input PGN: {input_pgn_path}")
    print(f"Processing {len(cql_scripts)} CQL script(s)...")

    for script_path in cql_scripts:
        script_name = script_path.stem # Get filename without extension
        # Create a unique output file name for this script's results
        temp_output_pgn = output_path / f"{script_name}_output.pgn"

        command = [
            str(cql_bin_path),
            "-i", str(input_pgn_path),
            "-o", str(temp_output_pgn),
            str(script_path)
        ]

        print(f"\nRunning script: {script_path.name}...")
        print(f"Command: {' '.join(command)}")

        try:
            # Run CQL, wait for it to complete, capture output
            process = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            print("CQL execution successful.")
            if process.stdout:
                print("CQL Output:\n---BEGIN---\n" + process.stdout + "\n---END---")
            if process.stderr:
                 print("CQL Error Output:\n---BEGIN---\n" + process.stderr + "\n---END---")

            # Count games in the output PGN
            game_count = count_games_in_pgn(temp_output_pgn)
            results[script_path.name] = game_count
            print(f"Result: Found {game_count} matching game(s).")

        except subprocess.CalledProcessError as e:
            print(f"Error running CQL script '{script_path.name}':")
            print(f"Return code: {e.returncode}")
            if e.stdout:
                print(f"Stdout:\n{e.stdout}")
            if e.stderr:
                print(f"Stderr:\n{e.stderr}")
            results[script_path.name] = "Error" # Indicate error in results
        except FileNotFoundError:
             print(f"Error: Could not execute CQL binary. Check path: {cql_binary}")
             return None # Abort if CQL binary cannot be run
        except Exception as e:
            print(f"An unexpected error occurred while processing {script_path.name}: {e}")
            results[script_path.name] = "Error"


    return results

def main():
    parser = argparse.ArgumentParser(description="Run CQL scripts against a PGN file and report game counts.")

    parser.add_argument("pgn_file", help="Path to the input PGN database file.")
    parser.add_argument("cql_binary", help="Path to the CQL executable binary.")
    parser.add_argument("scripts_location", help="Path to a single .cql script or a directory containing .cql scripts.")
    parser.add_argument("-o", "--output_dir", default=None, help="Directory to store temporary output PGN files (optional, default is a temporary directory).")
    parser.add_argument("--keep_output", action="store_true", help="Keep the temporary output PGN files after processing.")

    args = parser.parse_args()

    cql_scripts = find_cql_scripts(args.scripts_location)

    if not cql_scripts:
        print("No CQL scripts found to process.")
        return

    # Use a temporary directory if no output dir is specified
    if args.output_dir:
        output_directory = args.output_dir
        cleanup_needed = False
    else:
        temp_dir = tempfile.mkdtemp(prefix="cql_results_")
        output_directory = temp_dir
        cleanup_needed = not args.keep_output # Only clean up temp dir if --keep_output is not set
        print(f"Using temporary output directory: {output_directory}")


    stats = run_cql_analysis(args.pgn_file, args.cql_binary, cql_scripts, output_directory)

    if stats:
        print("\n--- Statistics ---")
        for script, count in stats.items():
            print(f"{script}: {count}")
        print("------------------")

    # Clean up the temporary directory if needed
    if cleanup_needed:
        try:
            shutil.rmtree(output_directory)
            print(f"Removed temporary directory: {output_directory}")
        except Exception as e:
            print(f"Warning: Could not remove temporary directory {output_directory}: {e}")
    elif not args.keep_output and args.output_dir:
         print(f"Output PGN files saved in: {output_directory}")
    elif args.keep_output:
         print(f"Output PGN files kept in: {output_directory}")


if __name__ == "__main__":
    main()