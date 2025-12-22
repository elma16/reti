#!/usr/bin/env python3
"""
FCE Table Analyzer — Flask app
- Runs all CQL scripts in parallel on an uploaded PGN
- Fast total-game counting for big PGNs (tag scan)
- Robust extraction from CQL outputs (FEN headers OR CQL comments)
- Lichess Tablebase proxy for chessboard buttons
"""

import os
import re
import mmap
import tempfile
import subprocess
from pathlib import Path
from functools import lru_cache
from typing import Any

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, render_template, request, jsonify, Response
import chess
import chess.pgn

# ---------------------- Config (update paths as needed) ----------------------
CQL_BINARY = "/Users/elliottmacneil/python/chess-stuff/reti/bins/cql6-1/cql"
CQL_SCRIPTS_DIR = "/Users/elliottmacneil/python/chess-stuff/reti/cql-files/FCE/table"
MIN_CQL_MATCHES = 2
TB_URL = "https://tablebase.lichess.ovh/standard"  # official Lichess TB

# Concurrency: number of scripts to run at once
MAX_WORKERS = min(8, (os.cpu_count() or 2))

# ------------------------------ Flask setup ---------------------------------
app = Flask(__name__, template_folder="templates")  # ensure templates/ exists
app.config["MAX_CONTENT_LENGTH"] = None
app.config["UPLOAD_FOLDER"] = tempfile.gettempdir()

# ------------------------------ Fast counters --------------------------------
RESULT_TAG = re.compile(rb'\[Result\s+"(?:1-0|0-1|1/2-1/2|\*)"\]')
EVENT_TAG = re.compile(rb'\[Event\s+"')


def fast_count_games_in_file(pgn_path: str) -> int:
    """Very fast count by scanning tags; fallback to slow parse if needed."""
    try:
        with open(pgn_path, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                n = len(RESULT_TAG.findall(mm))
                if n == 0:
                    n = len(EVENT_TAG.findall(mm))
                return n
    except Exception:
        return count_total_games_in_pgn(pgn_path)


def count_total_games_in_pgn(pgn_path: str) -> int:
    count = 0
    try:
        with open(pgn_path, encoding="utf-8", errors="replace") as pgn_file:
            while chess.pgn.read_game(pgn_file):
                count += 1
    except Exception as e:
        print(f"[WARN] Slow count failed: {e}")
        return 0
    return count


# ------------------------------ Utilities ------------------------------------
ENDING_NAMES = {
    "1-4BN": "1.4 Bishop + Knight vs King",
    "2-0Pp": "2 Pawn Endings",
    "2-1P": "2 King + Pawn vs King",
    "3-1Np": "3.1 Knight vs Pawns",
    "3-2NN": "3.2 Knight vs Knight",
    "4-1Bp": "4.1 Bishop vs Pawns",
    "4-2scBB": "4.2 Bishop vs Bishop (Same Colour)",
    "4-3ocBB": "4.3 Bishop vs Bishop (Opposite Colour)",
    "5-0BN": "5 Bishop vs Knight",
    "6-1-0RP": "6.1 Rook vs Pawns",
    "6-2-0Rr": "6.2 Rook vs Rook",
    "6-2-1RPr": "6.2 A1 Rook + Pawn vs Rook",
    "6-2-2RPPr": "6.2 A2 Rook + Two Pawns vs Rook",
    "6-3RRrr": "6.3 Two Rooks vs Two Rooks",
    "7-1RN": "7.1 Rook vs Knight",
    "7-2RB": "7.2 Rook vs Bishop",
    "8-1RNr": "8.1 Rook + Knight vs Rook",
    "8-1RNrPp": "8.1 Rook + Knight vs Rook (with pawns)",
    "8-2RBr": "8.2 Rook + Bishop vs Rook",
    "8-2RBrPp": "8.2 Rook + Bishop vs Rook (with pawns)",
    "8-3RAra": "8.3 Rook + Minor Piece vs Rook + Minor Piece",
    "9-1Qp": "9.1 Queen vs Pawns",
    "9-2Qq": "9.2 Queen vs Queen",
    "9-3QPq": "9.3 Queen + Pawn vs Queen",
    "10-1Qa": "10.1 Queen vs One Minor Piece",
    "10-2Qr": "10.2 Queen vs Rook",
    "10-2QrPp": "10.2 Queen vs Rook (with pawns)",
    "10-3Qaa": "10.3 Queen vs Two Minor Pieces",
    "10-4Qra": "10.4 Queen vs Rook + Minor Piece",
    "10-5Qrr": "10.5 Queen vs Two Rooks",
    "10-6Qaaa": "10.6 Queen vs Three Minor Pieces",
    "10-7QAq": "10.7 Queen and Minor Piece vs Queen",
    "10-7-1Qbrr": "10.7 Queen + Bishop vs Two Rooks",
    "10-7-1QbrrPp": "10.7 Queen + Bishop vs Two Rooks (with pawns)",
}


def natural_sort_key(script_name: str):
    parts = script_name.split("-")
    if len(parts) >= 2:
        try:
            major = int(parts[0])
            minor = (
                int(re.match(r"^(\d+)", parts[1]).group(1))
                if re.match(r"^(\d+)", parts[1])
                else 0
            )
            return (major, minor, script_name)
        except ValueError:
            pass
    return (999, 999, script_name)


def parse_side_to_move_from_fen(fen: str) -> str:
    try:
        stm = fen.split()[1].strip()
        return "White" if stm == "w" else "Black"
    except Exception:
        return "?"


def traverse_all_nodes_count_cql(
    game: chess.pgn.Game,
) -> tuple[int, chess.Board | None, chess.pgn.ChildNode | None]:
    count = 0
    first_board = None
    first_node = None

    def walk(node: chess.pgn.GameNode, board: chess.Board):
        nonlocal count, first_board, first_node
        if node.comment and ("cql" in node.comment.lower()):
            count += 1
            if first_board is None:
                first_board = board.copy()
                first_node = node
        for var in node.variations:
            board.push(var.move)
            walk(var, board)
            board.pop()

    root = game
    walk(root, game.board())
    return count, first_board, first_node


def extract_positions_from_pgn(pgn_path: str, min_matches: int = MIN_CQL_MATCHES):
    positions: list[dict[str, Any]] = []
    total_games = 0
    qualifying_games = 0
    try:
        with open(pgn_path, encoding="utf-8", errors="replace") as pgn_file:
            while True:
                game = chess.pgn.read_game(pgn_file)
                if game is None:
                    break
                total_games += 1
                H = game.headers
                white = H.get("White", "?")
                black = H.get("Black", "?")
                event = H.get("Event", "?")
                date = H.get("Date", "?")
                result = H.get("Result", "*")

                # Case 1: FEN header output from CQL
                if H.get("SetUp", "") == "1" and "FEN" in H:
                    fen = H["FEN"]
                    cql_count = 1  # treat FEN-only game as one match
                    if cql_count >= min_matches:
                        qualifying_games += 1
                        positions.append(
                            {
                                "fen": fen,
                                "white": white,
                                "black": black,
                                "event": event,
                                "date": date,
                                "result": result,
                                "move_number": "-",
                                "game_number": total_games,
                                "cql_count_in_game": cql_count,
                                "side_to_move": parse_side_to_move_from_fen(fen),
                            }
                        )
                    continue

                # Case 2: comments-based outputs
                cql_count, first_board, first_node = traverse_all_nodes_count_cql(game)
                if cql_count >= min_matches and first_board is not None:
                    qualifying_games += 1
                    move_label = "-"
                    if first_node and first_node.parent:
                        move_label = (
                            f"{first_board.fullmove_number}."
                            if first_board.turn == chess.WHITE
                            else f"{first_board.fullmove_number}..."
                        )
                    positions.append(
                        {
                            "fen": first_board.fen(),
                            "white": white,
                            "black": black,
                            "event": event,
                            "date": date,
                            "result": result,
                            "move_number": move_label,
                            "game_number": total_games,
                            "cql_count_in_game": cql_count,
                            "side_to_move": "White"
                            if first_board.turn == chess.WHITE
                            else "Black",
                        }
                    )
    except Exception as e:
        print(f"[ERROR] extract_positions_from_pgn: {e}")
        return [], 0, 0
    return positions, total_games, qualifying_games


def run_cql_script(
    pgn_file: str, script_path: Path, output_dir: str
) -> tuple[str, bool, str]:
    """Run one CQL script; returns (script_name, ok, output_pgn or err)."""
    script_name = script_path.stem
    output_pgn = os.path.join(output_dir, f"{script_name}.pgn")
    try:
        result = subprocess.run(
            [CQL_BINARY, "-i", pgn_file, "-o", output_pgn, str(script_path)],
            capture_output=True,
            text=True,
            timeout=900,
        )
        if result.returncode != 0:
            return script_name, False, result.stderr.strip() or "CQL error"
        return script_name, True, output_pgn
    except subprocess.TimeoutExpired:
        return script_name, False, "timeout"
    except Exception as e:
        return script_name, False, str(e)


def analyze_pgn_with_fce_table(pgn_path: str, min_matches: int = MIN_CQL_MATCHES):
    cql_dir = Path(CQL_SCRIPTS_DIR)
    cql_scripts = sorted(cql_dir.glob("*.cql"), key=lambda p: natural_sort_key(p.stem))
    if not cql_scripts:
        return {"error": f"No CQL scripts found in {CQL_SCRIPTS_DIR}"}

    print("[INFO] Counting total games (fast) …")
    total_database_games = fast_count_games_in_file(pgn_path)
    print(f"[INFO] Total games in database: {total_database_games:,}")

    output_dir = tempfile.mkdtemp(prefix="fce_results_")
    results: dict[str, Any] = {}
    total_qualifying_games = 0

    # -------- Run all scripts in parallel --------
    print(f"[INFO] Running {len(cql_scripts)} CQL scripts with {MAX_WORKERS} workers …")
    futures = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for sp in cql_scripts:
            futures.append(pool.submit(run_cql_script, pgn_path, sp, output_dir))

        for fut in as_completed(futures):
            script_name, ok, out = fut.result()
            ending_name = ENDING_NAMES.get(script_name, script_name)
            if not ok:
                print(f"[CQL][FAIL] {script_name}: {out}")
                continue
            output_pgn = out
            positions, total_cql_games, qualifying_games = extract_positions_from_pgn(
                output_pgn, min_matches
            )
            print(
                f"[CQL][OK] {ending_name}: {qualifying_games} qualifying (from {total_cql_games})"
            )
            if qualifying_games > 0:
                results[script_name] = {
                    "ending_name": ending_name,
                    "qualifying_games": qualifying_games,
                    "total_games": total_cql_games,
                    "positions": positions,
                }
                total_qualifying_games += qualifying_games

    return results, total_qualifying_games, total_database_games


# ------------------------------ Routes ---------------------------------------
@app.route("/healthz")
def healthz() -> Response:
    return Response("ok", status=200, mimetype="text/plain")


@app.route("/")
def index():
    # Try to render the real template; if missing, use a simple fallback so you
    # don’t get a confusing browser-level 403 from an interceptor.
    try:
        return render_template("fce_table.html", min_matches=MIN_CQL_MATCHES)
    except Exception as e:
        print(f"[WARN] templates/fce_table.html not found or failed: {e}")
        html = """
        <html><body>
        <h1>FCE Analyzer</h1>
        <p><b>Warning</b>: could not render templates/fce_table.html<br>
        Ensure your working directory has a <code>templates/</code> folder containing <code>fce_table.html</code>.</p>
        <p>Try: <code>curl -v http://127.0.0.1:5000/healthz</code> (should return "ok").</p>
        </body></html>
        """
        return Response(html, status=200, mimetype="text/html")


@app.route("/analyze", methods=["POST"])
def analyze():
    if "pgn_file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["pgn_file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not file.filename.lower().endswith(".pgn"):
        return jsonify({"error": "File must be a .pgn file"}), 400

    min_matches = request.form.get("min_matches", MIN_CQL_MATCHES, type=int)

    tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".pgn", delete=False)
    tmp_path = tmp.name
    try:
        file.save(tmp_path)
        print(f"[INFO] Analyze: {file.filename} (min_matches={min_matches})")
        results, total_qualifying_games, total_database_games = (
            analyze_pgn_with_fce_table(tmp_path, min_matches)
        )

        if isinstance(results, dict) and "error" in results:
            return jsonify(results), 500

        for data in results.values():
            data["percentage"] = (
                (data["qualifying_games"] / total_database_games * 100.0)
                if total_database_games
                else 0.0
            )

        payload = {
            "success": True,
            "results": results,
            "total_endings": len(results),
            "total_qualifying_games": total_qualifying_games,
            "total_database_games": total_database_games,
            "min_matches": min_matches,
        }
        return jsonify(payload)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"error": f"Analysis failed: {e}"}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# Lichess Tablebase proxy (avoid CORS; small in-memory cache)
@lru_cache(maxsize=4096)
def _tb_fetch_cached(fen_underscored: str) -> requests.Response:
    return requests.get(TB_URL, params={"fen": fen_underscored}, timeout=6)


@app.route("/tablebase")
def tablebase():
    fen = request.args.get("fen", "")
    if not fen:
        return jsonify({"error": "Missing fen"}), 400
    fen_u = fen.replace(" ", "_")
    try:
        r = _tb_fetch_cached(fen_u)
    except requests.RequestException as e:
        return jsonify({"error": f"TB request failed: {e}"}), 502

    if r.status_code == 404:
        return ("", 404)
    if r.status_code in (400, 422):
        return jsonify({"error": "Bad or unsupported FEN"}), 400
    if not r.ok:
        return jsonify({"error": f"Upstream error {r.status_code}"}), 502

    try:
        data = r.json()
    except ValueError:
        return jsonify({"error": "Invalid JSON from TB"}), 502

    return jsonify(
        {
            "category": data.get("category"),
            "dtz": data.get("dtz"),
            "dtm": data.get("dtm"),
            "checkmate": data.get("checkmate"),
            "stalemate": data.get("stalemate"),
            "moves": data.get("moves", []),
        }
    )


if __name__ == "__main__":
    here = Path.cwd()
    print("FCE Table Analyzer Web App")
    print(f"- CQL binary      : {CQL_BINARY}")
    print(f"- CQL scripts dir : {CQL_SCRIPTS_DIR}")
    print(f"- Working dir     : {here}")
    print(f"- Templates dir   : {Path(app.template_folder).resolve()}")
    print(f"- Min CQL Matches : {MIN_CQL_MATCHES}")
    print(f"- Max workers     : {MAX_WORKERS}")
    print("Try:  http://127.0.0.1:5000/healthz  -> 'ok'")
    print("Then: http://127.0.0.1:5000/")
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
