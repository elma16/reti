import chess
import chess.engine
import chess.pgn

# Path to the PGN file
pgn_file_path = "/Users/elliottmacneil/python/chess-stuff/reti/test.pgn"  # Update with your PGN file path

# Function to evaluate a position
def evaluate_position(board, engine, time_limit=1.0):
    print('analysing...')
    with engine.analysis(board, chess.engine.Limit(time=time_limit)) as analysis:
        for info in analysis:
            if info.get("score"):
                return info["score"].relative.score(mate_score=10000)

# Analyzing the game
pawn_capture_evaluations = []

def analyze_game(pgn_path):
    with open(pgn_path) as pgn_file:
        game = chess.pgn.read_game(pgn_file)

    board = game.board()
    with chess.engine.SimpleEngine.popen_uci("/opt/homebrew/Cellar/stockfish/16/bin/stockfish") as engine:  # Replace with your Stockfish engine path
        for node in game.mainline():
            move = node.move
            board.push(move)
            print('move',move)
            # Check for the next node if it has a CQL comment
            if node.variations:  # Ensure there is a next move
                next_node = node.variation(0)
                if 'CQL' in next_node.comment:
                    # Evaluation before the capture (current position)
                    eval_before = evaluate_position(board, engine)
                    # Make the capture and evaluate after
                    capture_move = next_node.move
                    if board.is_legal(capture_move):
                        board.push(capture_move)
                        print('capture',capture_move)
                        eval_after = evaluate_position(board, engine)

                        # Record the evaluation difference and start/end files
                        start_file = chess.square_file(capture_move.from_square)
                        end_file = chess.square_file(capture_move.to_square)
                        pawn_capture_evaluations.append({
                            "move": board.san(capture_move),
                            "eval_before": eval_before,
                            "eval_after": eval_after,
                            "eval_diff": eval_after - eval_before,
                            "start_file": chess.FILE_NAMES[start_file],
                            "end_file": chess.FILE_NAMES[end_file]
                        })

                        # Pop the capture move to continue the iteration correctly
                        board.pop()
                    else:
                        print("Illegal move detected:", board.uci(capture_move))
            # Pop the original move at the end of the loop
            #if not node.is_end():
            #    board.pop()

# Run the analysis
analyze_game(pgn_file_path)

# Display the results
for evaluation in pawn_capture_evaluations:
    print(evaluation)
