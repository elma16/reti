#!/usr/bin/env python3
"""
Fundamental Chess Endings Table Analyzer

Analyzes a PGN file using CQL files that correspond to the FCE table.
Only counts games that have at least MIN_CQL_MATCHES CQL comments.
Displays results in a table format matching the FCE book.
"""

import os
import sys
import subprocess
import tempfile
import chess.pgn
from pathlib import Path

# Configuration
CQL_BINARY = "/Users/elliottmacneil/python/chess-stuff/reti/bins/cql6-1/cql"
CQL_SCRIPTS_DIR = "/Users/elliottmacneil/python/chess-stuff/reti/cql-files/FCE/table"
MIN_CQL_MATCHES = 2  # Minimum number of CQL comments required per game

# Mapping from CQL filename to readable ending name
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


def count_cql_comments_in_game(game):
    """
    Count the number of {CQL} comments in a game.
    Returns the count.
    """
    count = 0
    node = game

    while node is not None:
        if node.comment and "CQL" in node.comment:
            count += 1

        if node.variations:
            node = node.variations[0]
        else:
            node = None

    return count


def extract_positions_from_pgn(pgn_path, min_matches=MIN_CQL_MATCHES):
    """
    Extract FIRST position from games that have at least min_matches CQL comments.
    Returns:
        - List of position dicts (one per qualifying game)
        - Total number of games in the PGN
        - Number of games that met the minimum CQL match requirement
    """
    positions = []
    total_games = 0
    qualifying_games = 0

    try:
        with open(pgn_path, encoding="utf-8", errors="replace") as pgn_file:
            while True:
                game = chess.pgn.read_game(pgn_file)
                if game is None:
                    break

                total_games += 1

                # Count CQL comments in this game
                cql_count = count_cql_comments_in_game(game)

                # Skip games that don't meet minimum requirement
                if cql_count < min_matches:
                    continue

                qualifying_games += 1

                # Extract ONLY THE FIRST CQL position from this game
                board = game.board()
                move_num = 0
                found_first = False

                for node in game.mainline():
                    move = node.move
                    move_num += 1
                    comment = node.comment
                    board.push(move)

                    if comment and "CQL" in comment and not found_first:
                        fen = board.fen()

                        # Determine side to move
                        side_to_move = "White" if board.turn else "Black"

                        # Calculate full move number
                        full_move = (move_num + 1) // 2
                        if move_num % 2 == 1:
                            move_str = f"{full_move}."
                        else:
                            move_str = f"{full_move}..."

                        position_info = {
                            "fen": fen,
                            "white": game.headers.get("White", "?"),
                            "black": game.headers.get("Black", "?"),
                            "event": game.headers.get("Event", "?"),
                            "date": game.headers.get("Date", "?"),
                            "result": game.headers.get("Result", "*"),
                            "move_number": move_str,
                            "game_number": total_games,
                            "cql_count_in_game": cql_count,
                            "side_to_move": side_to_move,
                        }
                        positions.append(position_info)
                        found_first = True
                        break  # Only take first CQL position

    except Exception as e:
        print(f"Error extracting positions from {pgn_path}: {e}")
        return [], 0, 0

    return positions, total_games, qualifying_games


def run_cql_script(pgn_file, cql_script_path, output_dir):
    """
    Run a single CQL script against a PGN file.
    Returns tuple: (output_pgn_path, success)
    """
    script_name = cql_script_path.stem
    output_pgn = os.path.join(output_dir, f"{script_name}.pgn")

    try:
        result = subprocess.run(
            [CQL_BINARY, "-i", pgn_file, "-o", output_pgn, str(cql_script_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            print(f"  CQL error for {script_name}: {result.stderr}")
            return None, False

        return output_pgn, True

    except subprocess.TimeoutExpired:
        print(f"  CQL timeout for {script_name}")
        return None, False
    except Exception as e:
        print(f"  Error running CQL script {script_name}: {e}")
        return None, False


def count_total_games_in_pgn(pgn_path):
    """Count total number of games in the original PGN file."""
    count = 0
    try:
        with open(pgn_path, encoding="utf-8", errors="replace") as pgn_file:
            while True:
                game = chess.pgn.read_game(pgn_file)
                if game is None:
                    break
                count += 1
    except Exception as e:
        print(f"Error counting games: {e}")
        return 0
    return count


def natural_sort_key(script_name):
    """
    Natural sorting key for section numbers like "10-2Qr" to sort numerically.
    Extracts: major number (10), minor number (2), then rest of string.
    """
    import re

    parts = script_name.split("-")
    if len(parts) >= 2:
        try:
            major = int(parts[0])
            # Extract minor number from second part (e.g., "2Qr" -> 2)
            minor_match = re.match(r"^(\d+)", parts[1])
            minor = int(minor_match.group(1)) if minor_match else 0
            return (major, minor, script_name)
        except ValueError:
            pass
    return (999, 999, script_name)  # Put unparseable names at end


def analyze_pgn_with_fce_table(pgn_path, min_matches=MIN_CQL_MATCHES):
    """
    Run all FCE table CQL scripts against the PGN.
    Only count games with at least min_matches CQL comments.
    Returns dict of results and total database size.
    """
    cql_dir = Path(CQL_SCRIPTS_DIR)
    cql_scripts = sorted(cql_dir.glob("*.cql"), key=lambda p: natural_sort_key(p.stem))

    if not cql_scripts:
        print(f"Error: No CQL scripts found in {CQL_SCRIPTS_DIR}")
        return None

    # Count total games in original database for percentage calculation
    print("\nCounting total games in database...")
    total_database_games = count_total_games_in_pgn(pgn_path)
    print(f"Total games in database: {total_database_games:,}")

    print(f"\nFound {len(cql_scripts)} CQL scripts")
    print(f"Minimum CQL matches per game: {min_matches}\n")

    # Create temporary output directory
    output_dir = tempfile.mkdtemp(prefix="fce_table_results_")

    results = {}
    total_qualifying_games = 0

    for i, script_path in enumerate(cql_scripts, 1):
        script_name = script_path.stem
        ending_name = ENDING_NAMES.get(script_name, script_name)

        print(f"[{i}/{len(cql_scripts)}] Processing: {ending_name}")

        # Run CQL script
        output_pgn, success = run_cql_script(pgn_path, script_path, output_dir)

        if not success or not output_pgn:
            print("  -> Skipped (CQL failed)")
            continue

        # Extract positions from qualifying games
        positions, total_games, qualifying_games = extract_positions_from_pgn(
            output_pgn, min_matches
        )

        print(
            f"  -> {qualifying_games} games with >={min_matches} CQL comments (from {total_games} total matches)"
        )

        if qualifying_games > 0:
            results[script_name] = {
                "ending_name": ending_name,
                "qualifying_games": qualifying_games,
                "total_games": total_games,
                "positions": positions,
                "pgn_file": output_pgn,
            }
            total_qualifying_games += qualifying_games

    return results, total_qualifying_games, total_database_games


def format_table_output(results, total_qualifying_games, total_database_games):
    """
    Format results as a table matching the FCE book format.
    Percentages are calculated as (count / total_database_games) * 100
    to match the book's methodology.
    """
    if not results:
        print("\nNo endings found!")
        return

    print("\n" + "=" * 80)
    print("FUNDAMENTAL CHESS ENDINGS - ANALYSIS RESULTS")
    print("=" * 80)
    print(f"\nTotal games in database: {total_database_games:,}")
    print(
        f"Total qualifying games (with >={MIN_CQL_MATCHES} CQL matches): {total_qualifying_games:,}"
    )
    print(f"Minimum CQL matches per game: {MIN_CQL_MATCHES}")
    print("\n" + "-" * 80)
    print(f"{'Ending Type':<50} {'Quantity':<15} {'Percentage':<10}")
    print("-" * 80)

    # Sort by ending name using natural sort
    sorted_results = sorted(results.items(), key=lambda x: natural_sort_key(x[0]))

    for script_name, data in sorted_results:
        ending_name = data["ending_name"]
        count = data["qualifying_games"]
        # Calculate percentage based on TOTAL DATABASE SIZE (like the book does)
        percentage = (
            (count / total_database_games * 100) if total_database_games > 0 else 0
        )

        print(f"{ending_name:<50} {count:<15,} {percentage:>6.2f}%")

    print("-" * 80)
    print()


def display_positions_summary(results):
    """
    Display a summary of positions available for each ending.
    """
    print("\n" + "=" * 80)
    print("POSITIONS SUMMARY")
    print("=" * 80)

    sorted_results = sorted(results.items(), key=lambda x: x[1]["ending_name"])

    for script_name, data in sorted_results:
        ending_name = data["ending_name"]
        positions = data["positions"]

        if positions:
            print(f"\n{ending_name}: {len(positions)} positions available")
            print(
                f"  First position: {positions[0]['white']} vs {positions[0]['black']}"
            )
            print(f"  PGN file: {data['pgn_file']}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python fce_table_analyzer.py <pgn_file> [min_cql_matches]")
        print(f"\nDefault min_cql_matches: {MIN_CQL_MATCHES}")
        sys.exit(1)

    pgn_path = sys.argv[1]

    if not os.path.exists(pgn_path):
        print(f"Error: PGN file not found: {pgn_path}")
        sys.exit(1)

    # Allow overriding MIN_CQL_MATCHES from command line
    min_matches = MIN_CQL_MATCHES
    if len(sys.argv) >= 3:
        try:
            min_matches = int(sys.argv[2])
        except ValueError:
            print(
                f"Warning: Invalid min_cql_matches value. Using default: {MIN_CQL_MATCHES}"
            )

    print(f"\nAnalyzing: {pgn_path}")
    print(f"CQL Scripts Directory: {CQL_SCRIPTS_DIR}")
    print(f"Minimum CQL matches per game: {min_matches}")

    # Run analysis
    result = analyze_pgn_with_fce_table(pgn_path, min_matches)

    if result is None:
        print("\nAnalysis failed!")
        sys.exit(1)

    results, total_qualifying_games, total_database_games = result

    # Display table
    format_table_output(results, total_qualifying_games, total_database_games)

    # Display positions summary
    display_positions_summary(results)

    print("\n" + "=" * 80)
    print("Analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
