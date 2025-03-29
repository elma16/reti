import argparse
import chess
import chess.pgn
import requests
from bs4 import BeautifulSoup
import time
import webbrowser


class TablebasePositionChecker:
    def __init__(self):
        pass

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
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            time.sleep(1)  # Add a delay to avoid overloading the server

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

    def process_pgn(self, pgn_file, target_result):
        """Process the PGN file and check positions with 'CQL' comment."""
        with open(pgn_file) as f:
            game = chess.pgn.read_game(f)
            while game:
                node = game
                while node:
                    if node.comment and "CQL" in node.comment:
                        board = node.board()
                        tablebase_result = self.check_tablebase_result(board)
                        if tablebase_result == target_result:
                            print("\nFound matching position!")
                            print(f"FEN: {board.fen()}")
                            print(f"Comment: {node.comment}")
                            print("\nOpening URLs...")
                            syzygy_url = self.get_syzygy_url(board)
                            print(f"Syzygy URL: {syzygy_url}")
                            webbrowser.open(syzygy_url)
                            lichess_url = self.get_lichess_url(board)
                            print(f"Lichess URL: {lichess_url}")
                            webbrowser.open(lichess_url)
                            break
                    node = node.variations[0] if node.variations else None
                game = chess.pgn.read_game(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check CQL positions in a PGN file against Syzygy tablebases."
    )
    parser.add_argument("pgn_file", help="Path to the PGN file")
    parser.add_argument(
        "target_result",
        choices=["win", "loss", "draw"],
        help="Desired result (win, loss, or draw)",
    )
    args = parser.parse_args()

    checker = TablebasePositionChecker()
    checker.process_pgn(args.pgn_file, args.target_result)
