import chess
import chess.engine
import webbrowser
from bs4 import BeautifulSoup
import requests
import time
import random


class TablebasePositionFinder:
    def __init__(self, engine_path="/opt/homebrew/bin/stockfish"):
        """Initialize with path to Stockfish engine."""
        self.engine_path = engine_path
        # engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)

    def generate_position(self, white_pieces, black_pieces):
        """Generate a valid chess position with given pieces."""
        # Convert piece strings to chess.Piece objects
        piece_map = {
            "K": chess.Piece(chess.KING, chess.WHITE),
            "Q": chess.Piece(chess.QUEEN, chess.WHITE),
            "R": chess.Piece(chess.ROOK, chess.WHITE),
            "B": chess.Piece(chess.BISHOP, chess.WHITE),
            "N": chess.Piece(chess.KNIGHT, chess.WHITE),
            "P": chess.Piece(chess.PAWN, chess.WHITE),
            "k": chess.Piece(chess.KING, chess.BLACK),
            "q": chess.Piece(chess.QUEEN, chess.BLACK),
            "r": chess.Piece(chess.ROOK, chess.BLACK),
            "b": chess.Piece(chess.BISHOP, chess.BLACK),
            "n": chess.Piece(chess.KNIGHT, chess.BLACK),
            "p": chess.Piece(chess.PAWN, chess.BLACK),
        }

        # Get all squares and shuffle them
        all_squares = list(chess.SQUARES)
        random.shuffle(all_squares)

        # Take the first n squares we need for our pieces
        squares = all_squares[: len(white_pieces) + len(black_pieces)]

        # Create board and place pieces
        board = chess.Board(None)  # Empty board

        # Place white pieces
        for piece, square in zip(white_pieces, squares[: len(white_pieces)]):
            board.set_piece_at(square, piece_map[piece])

        # Place black pieces
        for piece, square in zip(black_pieces, squares[len(white_pieces) :]):
            board.set_piece_at(square, piece_map[piece])

        if board.is_valid():
            return board

        return None

    def get_syzygy_url(self, board):
        """Generate Syzygy tablebase URL for the position."""
        fen = board.fen()
        return f"https://syzygy-tables.info/?fen={fen}"

    def get_lichess_url(self, board):
        """Generate Lichess URL for the position."""
        fen = board.fen()
        return f"https://lichess.org/analysis/{fen.replace(' ', '_')}"

    def check_tablebase_result(self, board):
        """Check the actual tablebase result from syzygy-tables.info."""
        url = self.get_syzygy_url(board)

        # Add headers to mimic a browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        try:
            # Make the request
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            time.sleep(1)

            status_badge = soup.find("h2", {"id": "status"})

            if status_badge:
                text = status_badge.text.lower()
                if "white is winning" in text:
                    return "win"
                elif "black is winning" in text:
                    return "loss"
                elif "draw" in text:
                    return "draw"
                else:
                    print(f"Unknown status: {text}")
                    return None
            return None

        except Exception as e:
            print(f"Error checking tablebase: {e}")
            return None


def main():
    # Get user input
    white_pieces = input("Enter white pieces (e.g., KQR): ").upper()
    black_pieces = input("Enter black pieces (e.g., kr): ").lower()
    target_eval = input("Desired evaluation (win/draw/loss): ").lower()

    # Validate input
    if len(white_pieces) + len(black_pieces) > 7:
        print("Error: Total pieces must be 7 or fewer for tablebase lookup")
        return

    if "K" not in white_pieces or "k" not in black_pieces:
        print("Error: Both sides must have exactly one king")
        return

    # if any of the inputs are empty
    if target_eval not in ["win", "draw", "loss"]:
        print("Error: Evaluation must be 'win', 'draw', or 'loss'")
        return

    # Create finder instance
    finder = TablebasePositionFinder()

    attempts = 0
    while True:
        attempts += 1
        print(f"\nAttempt {attempts}...")

        # Generate position
        board = finder.generate_position(white_pieces, black_pieces)
        if not board:
            print("Could not generate valid position, trying again...")
            continue

        print(f"Checking position: {board.fen()}")
        tablebase_result = finder.check_tablebase_result(board)
        print("Tablebase result:", tablebase_result)

        if tablebase_result == target_eval:
            print("\nFound matching position!")
            print(f"FEN: {board.fen()}")
            print("\nOpening URLs...")

            # Open Syzygy tablebase
            # syzygy_url = finder.get_syzygy_url(board)
            # print(f"Syzygy URL: {syzygy_url}")
            # webbrowser.open(syzygy_url)

            # Open Lichess analysis
            lichess_url = finder.get_lichess_url(board)
            print(f"Lichess URL: {lichess_url}")
            webbrowser.open(lichess_url)
            break

        time.sleep(1)


if __name__ == "__main__":
    main()
