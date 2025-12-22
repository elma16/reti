#!/usr/bin/env python3
"""
Flask Web App for CQL Endgame Analysis

Upload a PGN file and analyze it against 100 classical endgame patterns.
Results are displayed grouped by ending type with interactive chess diagrams.

Performance Notes (with Parallel Processing):
- Processes multiple CQL scripts simultaneously (default: 8 workers)
- Can reduce analysis time from hours to minutes
- Example: 100 scripts @ 30 seconds each:
  * Sequential: 50 minutes
  * Parallel (8 workers): ~7 minutes
- Memory usage: Increases with worker count (more processes = more RAM)
- Recommended workers: 4-8 for balance between speed and resources
- Configure MAX_WORKERS variable to adjust parallelization

File Size Handling:
- No hard file size limit (limited only by available RAM)
- Each CQL script has 5-minute timeout for large files
- Memory usage scales linearly with file size
- For databases with 10,000+ games, ensure sufficient RAM
"""

import os
import tempfile
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from flask import Flask, render_template, request, jsonify
import chess
import chess.pgn
import requests

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent.absolute()
TEMPLATE_DIR = SCRIPT_DIR / "templates"

app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
app.config["MAX_CONTENT_LENGTH"] = (
    None  # No file size limit - process what fits in memory
)
app.config["UPLOAD_FOLDER"] = tempfile.gettempdir()
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # Disable caching for development

# Configuration
CQL_BINARY = "/Users/elliottmacneil/python/chess-stuff/reti/bins/cql6-2/cql"
CQL_SCRIPTS_DIR = "/Users/elliottmacneil/python/chess-stuff/reti/cql-files/mates"

# Parallel processing configuration
# Number of CQL scripts to run in parallel (None = use all CPU cores)
# Recommended: 4-8 for good balance between speed and memory usage
MAX_WORKERS = min(8, multiprocessing.cpu_count())


def count_games_in_pgn(pgn_path):
    """Count the number of games in a PGN file."""
    count = 0
    try:
        with open(pgn_path, "r", encoding="utf-8", errors="replace") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                count += 1
    except Exception as e:
        print(f"Error counting games: {e}")
        return 0
    return count


def extract_cql_positions_from_pgn(pgn_path):
    """
    Extract all positions marked with {CQL} comment from a PGN file.
    Returns list of dicts with position info.
    """
    positions = []

    try:
        with open(pgn_path, encoding="utf-8", errors="replace") as pgn_file:
            game_num = 0
            while True:
                game = chess.pgn.read_game(pgn_file)
                if game is None:
                    break

                game_num += 1
                board = game.board()
                move_num = 0

                for node in game.mainline():
                    move = node.move
                    move_num += 1
                    comment = node.comment
                    board.push(move)

                    if comment == "CQL":
                        fen = board.fen()

                        # Calculate full move number (chess notation style)
                        full_move = (move_num + 1) // 2
                        if move_num % 2 == 1:  # White's move
                            move_str = f"{full_move}."
                        else:  # Black's move
                            move_str = f"{full_move}..."

                        position_info = {
                            "fen": fen,
                            "white": game.headers.get("White", "?"),
                            "black": game.headers.get("Black", "?"),
                            "event": game.headers.get("Event", "?"),
                            "date": game.headers.get("Date", "?"),
                            "result": game.headers.get("Result", "*"),
                            "move_number": move_str,
                            "game_number": game_num,
                        }
                        positions.append(position_info)
                        break  # Only take first CQL position per game

    except Exception as e:
        print(f"Error extracting positions from {pgn_path}: {e}")
        return []

    return positions


def run_cql_script(pgn_file, cql_script_path, output_dir):
    """
    Run a single CQL script against a PGN file.
    Returns tuple: (game_count, output_pgn_path)

    Note: For very large PGN files, each script can take several minutes.
    Memory usage scales with file size - ensure you have sufficient RAM.
    """
    script_name = cql_script_path.stem
    output_pgn = os.path.join(output_dir, f"{script_name}.pgn")

    try:
        result = subprocess.run(
            [CQL_BINARY, "-i", pgn_file, "-o", output_pgn, str(cql_script_path)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes per script for very large files
        )

        if result.returncode != 0:
            print(f"CQL error for {script_name}: {result.stderr}")
            return 0, None

        game_count = count_games_in_pgn(output_pgn)
        return game_count, output_pgn

    except subprocess.TimeoutExpired:
        print(f"CQL timeout for {script_name} (exceeded 5 minutes)")
        return 0, None
    except Exception as e:
        print(f"Error running CQL script {script_name}: {e}")
        return 0, None


def process_single_cql_script(args):
    """
    Wrapper function for parallel processing of a single CQL script.
    Returns tuple: (script_name, positions) or (script_name, None) on error.
    """
    pgn_file, cql_script_path, output_dir = args
    script_name = cql_script_path.stem

    try:
        # Run the CQL script
        game_count, output_pgn = run_cql_script(pgn_file, cql_script_path, output_dir)

        if game_count > 0 and output_pgn:
            # Extract positions from the matched games
            positions = extract_cql_positions_from_pgn(output_pgn)

            if positions:
                print(f"  ✓ {script_name}: Found {len(positions)} position(s)")
                return script_name, positions
            else:
                return script_name, None
        else:
            return script_name, None

    except Exception as e:
        print(f"  ✗ {script_name}: Error - {e}")
        return script_name, None


def analyze_pgn_with_cql(pgn_path):
    """
    Run all CQL scripts against the uploaded PGN in parallel.
    Returns dict of results grouped by ending type.

    Performance:
    - Uses ProcessPoolExecutor for parallel processing
    - Configurable worker count (default: min(8, CPU cores))
    - Can reduce analysis time from hours to minutes
    """
    cql_dir = Path(CQL_SCRIPTS_DIR)
    cql_scripts = sorted(cql_dir.glob("*.cql"))

    if not cql_scripts:
        return {"error": "No CQL scripts found"}

    # Create temporary output directory
    output_dir = tempfile.mkdtemp(prefix="cql_results_")

    print(f"\n{'=' * 60}")
    print(f"Starting parallel CQL analysis with {MAX_WORKERS} workers")
    print(f"Processing {len(cql_scripts)} CQL scripts...")
    print(f"{'=' * 60}\n")

    results = {}
    completed = 0

    # Prepare arguments for parallel processing
    script_args = [(pgn_path, script_path, output_dir) for script_path in cql_scripts]

    # Process scripts in parallel
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_script = {
            executor.submit(process_single_cql_script, args): args[1].stem
            for args in script_args
        }

        # Process results as they complete
        for future in as_completed(future_to_script):
            completed += 1
            script_name = future_to_script[future]

            try:
                script_name, positions = future.result()

                if positions:
                    results[script_name] = {
                        "count": len(positions),
                        "positions": positions,
                    }

                # Progress indicator
                print(
                    f"Progress: {completed}/{len(cql_scripts)} scripts completed ({completed * 100 // len(cql_scripts)}%)"
                )

            except Exception as e:
                print(f"  ✗ {script_name}: Exception - {e}")

    print(f"\n{'=' * 60}")
    print(f"Analysis complete: {len(results)} ending types found")
    print(f"{'=' * 60}\n")

    return results


@app.route("/")
def index():
    """Main page with upload form."""
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """Handle PGN upload and run CQL analysis."""
    if "pgn_file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["pgn_file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith(".pgn"):
        return jsonify({"error": "File must be a .pgn file"}), 400

    # Save uploaded file temporarily
    temp_pgn = tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False)
    temp_pgn_path = temp_pgn.name

    try:
        file.save(temp_pgn_path)

        print(f"Analyzing file: {file.filename}")
        print(f"File size: {os.path.getsize(temp_pgn_path)} bytes")

        # Run CQL analysis
        results = analyze_pgn_with_cql(temp_pgn_path)

        if "error" in results:
            print(f"Analysis error: {results['error']}")
            return jsonify(results), 500

        # Sort results by name
        sorted_results = dict(sorted(results.items()))

        total_positions = sum(len(r["positions"]) for r in sorted_results.values())

        print(
            f"Analysis complete: {len(sorted_results)} ending types, {total_positions} positions"
        )

        return jsonify(
            {
                "success": True,
                "results": sorted_results,
                "total_endings": len(sorted_results),
                "total_positions": total_positions,
            }
        )

    except Exception as e:
        print(f"Error during analysis: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

    finally:
        # Clean up uploaded file
        try:
            os.unlink(temp_pgn_path)
        except Exception:
            pass


@app.route("/tablebase", methods=["GET"])
def tablebase_proxy():
    """Proxy tablebase requests to avoid CORS issues."""
    fen = request.args.get("fen")

    if not fen:
        return jsonify({"error": "FEN parameter required"}), 400

    try:
        # Query Lichess tablebase API
        response = requests.get(
            "https://tablebase.lichess.ovh/standard", params={"fen": fen}, timeout=10
        )

        if response.ok:
            return jsonify(response.json())
        else:
            return jsonify({"error": "Tablebase lookup failed"}), response.status_code

    except requests.exceptions.RequestException as e:
        print(f"Tablebase query error: {e}")
        return jsonify({"error": "Network error querying tablebase"}), 503
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/download/<ending_type>")
def download_pgn(ending_type):
    """Download PGN file for a specific ending type."""
    # This would need session management to track temporary files
    # For now, return error
    return jsonify({"error": "Download not yet implemented"}), 501


if __name__ == "__main__":
    # Check if templates directory exists
    if not TEMPLATE_DIR.exists():
        print(f"ERROR: Templates directory not found at {TEMPLATE_DIR}")
        print("Please create a 'templates' folder in the same directory as this script")
        print("and place index.html inside it.")
        exit(1)

    if not (TEMPLATE_DIR / "index.html").exists():
        print(f"ERROR: index.html not found in {TEMPLATE_DIR}")
        print("Please make sure index.html is in the templates folder")
        exit(1)

    # Check if CQL binary exists
    if not os.path.exists(CQL_BINARY):
        print(f"WARNING: CQL binary not found at {CQL_BINARY}")
        print("Please update CQL_BINARY in the script")

    # Check if CQL scripts directory exists
    if not os.path.exists(CQL_SCRIPTS_DIR):
        print(f"WARNING: CQL scripts directory not found at {CQL_SCRIPTS_DIR}")
        print("Please update CQL_SCRIPTS_DIR in the script")

    print(f"Templates directory: {TEMPLATE_DIR}")
    print("Starting Flask app...")
    print("Open http://127.0.0.1:5000 in your browser")
    app.run(debug=True, port=5000)
