import requests
import webbrowser
import chess.pgn
import chess
import argparse
import random
import io
from env import api_key

"""
Chess Practice Tool

This script allows practicing chess positions in two modes:
1. Resigned Games: Practice positions where a player resigned
2. Ending Practice: Practice positions marked with {CQL} that are winning according to tablebases

Features:
- Random selection of games
- Specify the number of games to play
- Two practice modes
- Results tracking
"""

def get_tablebase_result(fen):
    """
    Query the Lichess tablebase API to check if a position is winning
    Returns a tuple (result, optimal_move) where result is 'win', 'loss', 'draw' or None if not found
    """
    try:
        response = requests.get(
            f'https://tablebase.lichess.ovh/standard',
            params={'fen': fen}
        ).json()
        
        if 'category' in response:
            return response['category'], response.get('moves', [{}])[0].get('uci', '')
        return None, None
    except Exception as e:
        print(f"Error querying tablebase: {e}")
        return None, None

def challenge_from_resigned_games(pgn_file, num_games, tally):
    """
    Practice positions from games that ended with a resignation.
    Randomly selects games from the PGN file.
    """
    # Load all games from the PGN file
    all_games = []
    with open(pgn_file) as file:
        while True:
            game = chess.pgn.read_game(file)
            if game is None:
                break
            result = game.headers.get("Result")
            if result in ("1-0", "0-1"):  # Only consider decisive games
                all_games.append(game)
    
    if not all_games:
        print("No decisive games found in the PGN.")
        return
    
    print(f"Found {len(all_games)} decisive games in the PGN.")
    
    # Randomly select the specified number of games
    num_to_play = min(num_games, len(all_games))
    selected_games = random.sample(all_games, num_to_play)
    
    print(f"Selected {num_to_play} games for practice.")
    
    for i, game in enumerate(selected_games, 1):
        result = game.headers["Result"]
        winner_color = "white" if result == "1-0" else "black"
        fen = game.end().board().fen()
        
        print(f"\nGame {i}/{num_to_play}: Playing as {winner_color}")
        print(f"From: {game.headers.get('White', '?')} vs {game.headers.get('Black', '?')}")
        print(f"Event: {game.headers.get('Event', 'Unknown')}")
        
        response = requests.post(
            'https://lichess.org/api/challenge/ai',
            headers={'Authorization': f'Bearer {api_key}'},
            data={
                'level': 8,
                'clock.limit': 60,
                'clock.increment': 1,
                'fen': fen,
                'color': winner_color
            }
        ).json()
        
        if 'fullId' in response:
            challenge_url = f"https://lichess.org/{response['fullId']}"
            print(f"Challenge created: {challenge_url}")
            webbrowser.open(challenge_url)
        else:
            print('Error creating challenge:', response)
            continue
        
        result_input = input("Game complete! Enter your result (w=win, d=draw, l=loss, q=quit): ").lower()
        if result_input == 'w':
            tally["wins"] += 1
        elif result_input == 'd':
            tally["draws"] += 1
        elif result_input == 'l':
            tally["losses"] += 1
        elif result_input == 'q':
            print("Quitting practice session.")
            break
        else:
            print("Invalid input. Result not counted.")

def find_cql_positions(pgn_file):
    cql_positions = []
    with open(pgn_file) as pgn:
        while True:
            game = chess.pgn.read_game(pgn)
            if game is None:
                break
            node = game
            while node.variations:
                node = node.variations[0]
                if node.comment and 'CQL' in node.comment:
                    board = node.board()
                    fen = board.fen()
                    to_move = 'white' if board.turn else 'black'
                    move_san = node.san()
                    cql_positions.append({
                        'fen': fen,
                        'to_move': to_move,
                        'game_info': f"{game.headers.get('White')} vs {game.headers.get('Black')}",
                        'move': move_san
                    })
    return cql_positions

def challenge_from_endgame_positions(pgn_file, num_games, tally, aim='win'):
    cql_positions = find_cql_positions(pgn_file)
    if not cql_positions:
        print("No positions marked with {CQL} found.")
        return
    
    target_positions = []
    print("Checking positions with tablebase...")
    for pos in cql_positions:
        result, best_move = get_tablebase_result(pos['fen'])
        if aim == 'win' and result == 'win':
            pos['best_move'] = best_move
            target_positions.append(pos)
        elif aim == 'draw' and result == 'draw':
            pos['best_move'] = best_move
            target_positions.append(pos)

    if not target_positions:
        print(f"No positions found matching aim '{aim}'.")
        return

    selected_positions = random.sample(target_positions, min(num_games, len(target_positions)))

    for i, pos in enumerate(selected_positions, 1):
        print(f"\nPosition {i}/{len(selected_positions)}: {pos['game_info']}")
        print(f"After move: {pos['move']} ({aim} scenario). Best tablebase move: {pos.get('best_move', 'N/A')}")
        response = requests.post(
            'https://lichess.org/api/challenge/ai',
            headers={'Authorization': f'Bearer {api_key}'},
            data={
                'level': 8,
                'clock.limit': 60,
                'clock.increment': 1,
                'fen': pos['fen'],
                'color': pos['to_move']
            }
        ).json()
        if 'fullId' in response:
            challenge_url = f"https://lichess.org/{response['fullId']}"
            print(f"Challenge created: {challenge_url}")
            webbrowser.open(challenge_url)
        else:
            print('Error:', response)
            continue

        result_input = input("Result (w=win, d=draw, l=loss, q=quit): ").lower()
        if result_input == 'w':
            tally["wins"] += 1
        elif result_input == 'd':
            tally["draws"] += 1
        elif result_input == 'l':
            tally["losses"] += 1
        elif result_input == 'q':
            break

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pgn", required=True)
    parser.add_argument("--mode", choices=["resigned", "endgame"], default="resigned")
    parser.add_argument("--num", type=int, default=5)
    parser.add_argument("--aim", choices=["win", "draw"], default="win")
    args = parser.parse_args()

    tally = {"wins": 0, "draws": 0, "losses": 0}

    if args.mode == "resigned":
        challenge_from_resigned_games(args.pgn, args.num, tally)
    else:
        challenge_from_endgame_positions(args.pgn, args.num, tally, aim=args.aim)

    print("\nResults:", tally)


def main():
    parser = argparse.ArgumentParser(description="Chess practice tool with resigned games and endgame practice")
    parser.add_argument("--pgn", required=True, help="Path to PGN file")
    parser.add_argument("--mode", choices=["resigned", "endgame"], default="resigned", 
                        help="Practice mode: resigned games or endgame positions")
    parser.add_argument("--num", type=int, default=5, help="Number of positions to practice")
    parser.add_argument("--aim", choices=["win", "draw"], default="win", 
                        help="Aim for endgame practice: win or draw")
    args = parser.parse_args()
    
    tally = {"wins": 0, "draws": 0, "losses": 0}
    
    print(f"Chess Practice Tool")
    print(f"Mode: {args.mode.capitalize()} Games")
    print(f"PGN File: {args.pgn}")
    print(f"Number of games requested: {args.num}")

    
    if args.mode == "resigned":
        challenge_from_resigned_games(args.pgn, args.num, tally)
    else:  # endgame mode
        challenge_from_endgame_positions(args.pgn, args.num, tally, aim=args.aim)
    
    print("\nFinal Results:")
    print(f"Wins: {tally['wins']}, Draws: {tally['draws']}, Losses: {tally['losses']}")

if __name__ == "__main__":
    main()