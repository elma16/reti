#!/usr/bin/env python3
"""
Endgame Trainer: Practice endgame positions from CQL-filtered PGN files.

This script:
1. Loads positions marked with {CQL} from specified PGN files
2. Randomly selects positions and validates them with tablebase
3. Challenges Stockfish on Lichess with validated positions
4. Three modes:
   - Attacking: Play side with more material, position must be theoretical win
   - Defending: Play side with less material, position must be theoretical draw
   - Losing: Play side with less material, position must be theoretical loss (learn how opponent wins)
"""

import chess
import chess.pgn
import requests
import webbrowser
import random
import argparse
import os
from pathlib import Path


LICHESS_TOKEN = os.environ.get("LICHESS_TOKEN")
MAX_TABLEBASE_PIECES = 7

# Material values for calculating material advantage
MATERIAL_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0
}


def calculate_material(board, color):
    """Calculate total material value for a given color."""
    material = 0
    for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
        material += len(board.pieces(piece_type, color)) * MATERIAL_VALUES[piece_type]
    return material


def get_attacking_defending_sides(board):
    """
    Determine which side has more material (attacking) and which has less (defending).
    Returns tuple: (attacking_color, defending_color, material_diff)
    """
    white_material = calculate_material(board, chess.WHITE)
    black_material = calculate_material(board, chess.BLACK)
    
    if white_material > black_material:
        return chess.WHITE, chess.BLACK, white_material - black_material
    elif black_material > white_material:
        return chess.BLACK, chess.WHITE, black_material - white_material
    else:
        return None, None, 0  # Equal material


def get_tablebase_result(fen):
    """
    Query the Lichess tablebase API to check the position result.
    Returns the category: 'win', 'loss', 'draw', or None if not found.
    """
    try:
        board = chess.Board(fen)
        if len(board.piece_map()) > MAX_TABLEBASE_PIECES:
            print(f"Skipping FEN (too many pieces > {MAX_TABLEBASE_PIECES}): {fen}")
            return None

        response = requests.get(
            "https://tablebase.lichess.ovh/standard", 
            params={"fen": fen},
            timeout=10
        ).json()

        if "category" not in response or response.get("checkmate") is None:
            print(f"Warning: Tablebase data incomplete for FEN: {fen}")
            return None

        return response["category"]

    except requests.exceptions.RequestException as e:
        print(f"Network error querying tablebase: {e}")
        return None
    except Exception as e:
        print(f"Error processing tablebase response: {e}")
        return None


def extract_cql_positions_from_pgn(pgn_path):
    """
    Extract all positions marked with {CQL} comment from a PGN file.
    Returns list of (fen, white_player, black_player) tuples.
    """
    positions = []
    
    try:
        with open(pgn_path, encoding="utf-8", errors="replace") as pgn_file:
            while True:
                game = chess.pgn.read_game(pgn_file)
                if game is None:
                    break
                
                board = game.board()
                for node in game.mainline():
                    move = node.move
                    comment = node.comment
                    board.push(move)
                    
                    if comment == "CQL":
                        fen = board.fen()
                        white = game.headers.get("White", "?")
                        black = game.headers.get("Black", "?")
                        positions.append((fen, white, black))
                        break  # Only take first CQL position per game
                        
    except FileNotFoundError:
        print(f"Error: File not found: {pgn_path}")
        return []
    except Exception as e:
        print(f"Error reading PGN file {pgn_path}: {e}")
        return []
    
    return positions


def find_valid_position(positions, play_as_side, max_attempts=1000):
    """
    Randomly select positions and validate with tablebase until finding a valid one.
    This function modifies the positions list in-place to ensure no replacement.
    
    play_as_side: 'attacking', 'defending', or 'losing'
    Returns: (fen, player_color, white_player, black_player) or None if not found
    """
    if not positions:
        print("No positions available!")
        return None
    
    attempts = 0
    checked_indices = []
    
    while len(checked_indices) < len(positions) and attempts < max_attempts:
        attempts += 1
        
        # Pick a random position we haven't checked yet
        available_indices = [i for i in range(len(positions)) if i not in checked_indices]
        if not available_indices:
            print("Exhausted all available positions!")
            return None
            
        idx = random.choice(available_indices)
        checked_indices.append(idx)
        
        fen, white_player, black_player = positions[idx]
        board = chess.Board(fen)
        
        # Skip if too many pieces
        if len(board.piece_map()) > MAX_TABLEBASE_PIECES:
            continue
        
        # Determine attacking and defending sides
        attacking_color, defending_color, material_diff = get_attacking_defending_sides(board)
        
        if attacking_color is None:
            print(f"Skipping position (equal material): {fen}")
            continue
        
        # Query tablebase
        print(f"Attempt {attempts}: Checking position...")
        tb_result = get_tablebase_result(fen)
        
        if tb_result is None:
            continue
        
        # Determine which color we're playing as and what result we need
        if play_as_side == 'attacking':
            player_color = attacking_color
            # Position must be winning for the attacking side
            if board.turn == attacking_color:
                required_result = 'win'
            else:
                required_result = 'loss'  # It's defender's turn, so attacking side wins
        elif play_as_side == 'defending':
            player_color = defending_color
            # Position must be a draw for the defending side
            required_result = 'draw'
        else:  # losing
            player_color = defending_color  # Play the side with less material
            # Position must be a loss for us (win for opponent)
            if board.turn == defending_color:
                required_result = 'loss'  # We're to move and losing
            else:
                required_result = 'win'  # Opponent to move and winning
        
        if tb_result == required_result:
            color_name = "white" if player_color == chess.WHITE else "black"
            if play_as_side == 'losing':
                side_type = "losing"
            else:
                side_type = "attacking" if play_as_side == 'attacking' else "defending"
            print(f"✓ Found valid position! Playing as {color_name} ({side_type} side)")
            print(f"  Material: W={calculate_material(board, chess.WHITE)}, B={calculate_material(board, chess.BLACK)}")
            print(f"  Tablebase: {tb_result}")
            
            # Remove this position so it won't be used again in this session
            positions.pop(idx)
            
            return fen, player_color, white_player, black_player
        else:
            print(f"  Position has result '{tb_result}' but need '{required_result}', continuing...")
    
    print(f"Could not find valid position after {attempts} attempts")
    return None


def challenge_stockfish(fen, player_color, level=8, time_limit=60, increment=2):
    """
    Create a Lichess challenge against Stockfish from the given position.
    """
    color_str = "white" if player_color == chess.WHITE else "black"
    
    try:
        response = requests.post(
            "https://lichess.org/api/challenge/ai",
            headers={"Authorization": f"Bearer {LICHESS_TOKEN}"},
            data={
                "level": level,
                "clock.limit": time_limit,
                "clock.increment": increment,
                "fen": fen,
                "color": color_str,
            },
            timeout=10,
        ).json()

        if "challenge" in response and "fullId" in response["challenge"]:
            challenge_url = f"https://lichess.org/{response['challenge']['fullId']}"
            print(f"Challenge created: {challenge_url}")
            webbrowser.open(challenge_url)
            return True
        elif "id" in response:
            challenge_url = f"https://lichess.org/{response['id']}"
            print(f"Challenge created: {challenge_url}")
            webbrowser.open(challenge_url)
            return True
        else:
            print(f"Error creating challenge: {response.get('error', response)}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Network error creating challenge: {e}")
        return False
    except Exception as e:
        print(f"Error creating challenge: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Practice endgame positions from CQL-filtered PGN files with tablebase validation."
    )
    
    parser.add_argument(
        "pgn_files",
        nargs="+",
        help="PGN file(s) to use for positions"
    )
    parser.add_argument(
        "-s", "--side",
        choices=["attacking", "defending", "losing"],
        required=True,
        help="Play as attacking side (need to win), defending side (need to draw), or losing side (learn how opponent wins)"
    )
    parser.add_argument(
        "-n", "--num-games",
        type=int,
        default=1,
        help="Number of games to play (default: 1)"
    )
    parser.add_argument(
        "-l", "--level",
        type=int,
        default=8,
        choices=range(1, 9),
        help="Stockfish level (1-8, default: 8)"
    )
    parser.add_argument(
        "-t", "--time",
        type=int,
        default=60,
        help="Time limit in seconds (default: 60)"
    )
    parser.add_argument(
        "-i", "--increment",
        type=int,
        default=2,
        help="Increment in seconds (default: 2)"
    )
    
    args = parser.parse_args()
    
    # Check for Lichess token
    if not LICHESS_TOKEN:
        print("Error: LICHESS_TOKEN environment variable not set!")
        print("Please set it with: export LICHESS_TOKEN='your_token_here'")
        return
    
    # Load all positions from specified PGN files
    print(f"Loading positions from {len(args.pgn_files)} file(s)...")
    all_positions = []
    
    for pgn_file in args.pgn_files:
        print(f"  Reading: {pgn_file}")
        positions = extract_cql_positions_from_pgn(pgn_file)
        print(f"    Found {len(positions)} CQL position(s)")
        all_positions.extend(positions)
    
    print(f"\nTotal positions loaded: {len(all_positions)}")
    
    if not all_positions:
        print("No positions found! Make sure your PGN files contain games with {CQL} comments.")
        return
    
    # Track results
    tally = {"wins": 0, "draws": 0, "losses": 0}
    
    # Note: all_positions list is modified in-place by find_valid_position()
    # Each used position is removed, ensuring no repeats within this session
    
    # Play n games
    for game_num in range(1, args.num_games + 1):
        print(f"\n{'='*60}")
        print(f"Game {game_num}/{args.num_games}")
        print(f"{'='*60}")
        
        # Find a valid position
        result = find_valid_position(all_positions, args.side)
        
        if result is None:
            print("Could not find a valid position. Skipping this game.")
            continue
        
        fen, player_color, white_player, black_player = result
        
        print(f"\nPosition from: {white_player} vs {black_player}")
        print(f"FEN: {fen}")
        print(f"Playing as: {'white' if player_color == chess.WHITE else 'black'}")
        
        # Challenge Stockfish
        success = challenge_stockfish(
            fen, player_color, 
            level=args.level, 
            time_limit=args.time, 
            increment=args.increment
        )
        
        if not success:
            print("Failed to create challenge. Skipping this game.")
            continue
        
        # Wait for user to complete the game and report result
        while True:
            result_input = input(
                "\nGame complete! Enter result (w=win, d=draw, l=loss, s=skip, q=quit): "
            ).lower().strip()
            
            if result_input == "w":
                tally["wins"] += 1
                break
            elif result_input == "d":
                tally["draws"] += 1
                break
            elif result_input == "l":
                tally["losses"] += 1
                break
            elif result_input == "s":
                print("Skipping this game (not counted).")
                break
            elif result_input == "q":
                print("\nQuitting practice session.")
                print(f"Final tally: {tally['wins']}W - {tally['draws']}D - {tally['losses']}L")
                return
            else:
                print("Invalid input. Please enter w, d, l, s, or q.")
    
    # Print final results
    print(f"\n{'='*60}")
    print("Practice session complete!")
    print(f"{'='*60}")
    print(f"Final results: {tally['wins']}W - {tally['draws']}D - {tally['losses']}L")
    total_games = tally['wins'] + tally['draws'] + tally['losses']
    if total_games > 0:
        win_rate = (tally['wins'] / total_games) * 100
        print(f"Win rate: {win_rate:.1f}%")


if __name__ == "__main__":
    main()
