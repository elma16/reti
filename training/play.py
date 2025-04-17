import requests
import webbrowser
import chess.pgn
import chess
import argparse
import random
from training.env import api_key  # Make sure you have an env.py file with your Lichess API key
import time

"""
Chess Practice Tool

Modes:
1. Resigned Games: Practice positions where a player resigned.
2. Endgame Practice (from PGN): Practice positions from PGN marked {CQL} (<= 7 pieces).
3. Random Endgame: Generate random positions with specific material (<= 7 pieces) and practice.

Features:
- Random selection/generation of positions.
- Specify the number of games to play.
- Multiple practice modes.
- Results tracking using Lichess tablebase API and AI challenges.
"""


MAX_TABLEBASE_PIECES = 7  # Define the maximum number of pieces for tablebase lookup
MAX_GENERATION_ATTEMPTS = 1000  # Limit attempts for random generation


def get_tablebase_result(fen):
    """
    Query the Lichess tablebase API to check if a position is winning
    Returns a tuple (result, optimal_move) where result is 'win', 'loss', 'draw' or None if not found
    """
    try:
        # Check piece count locally before querying the API
        board = chess.Board(fen)
        if len(board.piece_map()) > MAX_TABLEBASE_PIECES:
            print(f"Skipping FEN (too many pieces > {MAX_TABLEBASE_PIECES}): {fen}")
            return None, None

        response = requests.get(
            "https://tablebase.lichess.ovh/standard", params={"fen": fen}
        ).json()

        # Check if the response indicates an error or missing data, which can happen
        # even for <= 7 pieces if the specific endgame isn't covered or server issues
        if "category" not in response or response.get("checkmate") is None:
            # It's possible the API returns data but not the category/moves for certain positions
            # or if there's an error not caught by the exception block.
            print(
                f"Warning: Tablebase data incomplete or unavailable for FEN: {fen}. Response: {response}"
            )
            return None, None

        # Extract category and best move if available
        category = response["category"]  # e.g., "win", "loss", "draw"
        best_move_uci = ""
        if (
            response.get("moves")
            and isinstance(response["moves"], list)
            and len(response["moves"]) > 0
        ):
            # Ensure 'moves' is a non-empty list and access the first move's UCI
            best_move_info = response["moves"][0]
            if isinstance(best_move_info, dict) and "uci" in best_move_info:
                best_move_uci = best_move_info["uci"]

        return category, best_move_uci

    except requests.exceptions.RequestException as e:
        print(f"Network error querying tablebase: {e}")
        return None, None
    except Exception as e:
        print(f"Error processing tablebase response for FEN {fen}: {e}")
        return None, None


def challenge_from_resigned_games(pgn_file, num_games, tally):
    """
    Practice positions from games that ended with a resignation.
    Randomly selects games from the PGN file.
    """
    all_games = []
    try:
        with open(pgn_file, encoding="latin-1") as file:
            while True:
                # Use headers=False initially for speed if you only need the end position later
                game = chess.pgn.read_game(file)
                if game is None:
                    break
                # Check for result header later only if needed
                all_games.append(game)
    except FileNotFoundError:
        print(f"Error: PGN file not found at {pgn_file}")
        return
    except Exception as e:
        print(f"Error reading PGN file: {e}")
        return

    decisive_games = [g for g in all_games if g.headers.get("Result") in ("1-0", "0-1")]

    if not decisive_games:
        print("No decisive games found in the PGN.")
        return

    print(f"Found {len(decisive_games)} decisive games in the PGN.")

    num_to_play = min(num_games, len(decisive_games))
    if num_to_play <= 0:
        print("No games to play.")
        return

    selected_games = random.sample(decisive_games, num_to_play)

    print(f"Selected {num_to_play} games for practice.")

    for i, game in enumerate(selected_games, 1):
        result = game.headers["Result"]
        # Determine the color of the player *who did not resign*
        # The game ends *after* the loser's final move, so the board().turn is the winner's turn.
        # However, it's safer to rely on the result header.
        winner_color = "white" if result == "1-0" else "black"
        # Get the board state *before* the final move (the resigned position)
        # This requires navigating to the second-to-last node if the game has moves.
        final_node = game.end()
        if final_node.parent:  # Check if there's a previous move
            board_before_resign = final_node.parent.board()
            fen = board_before_resign.fen()
            # The player to move in the FEN is the one who resigned (the loser)
            # We want to play as the *winner*
            player_color_to_challenge = winner_color
        else:  # Game might have ended without moves? Unlikely but handle it.
            print(f"Warning: Game {i} has no moves. Using initial position.")
            fen = game.board().fen()
            player_color_to_challenge = winner_color  # Or decide based on context

        print(f"\nGame {i}/{num_to_play}: Playing as {player_color_to_challenge}")
        print(
            f"From: {game.headers.get('White', '?')} vs {game.headers.get('Black', '?')}"
        )
        print(f"Event: {game.headers.get('Event', 'Unknown')}")
        print(f"Position FEN: {fen}")

        try:
            response = requests.post(
                "https://lichess.org/api/challenge/ai",
                headers={"Authorization": f"Bearer {api_key}"},
                data={
                    "level": 8,  # Consider making level configurable
                    "clock.limit": 60,  # Increased time slightly
                    "clock.increment": 2,
                    "fen": fen,
                    "color": player_color_to_challenge,  # Play as the winner
                },
                timeout=10,  # Add a timeout
            ).json()

            if "challenge" in response and "fullId" in response["challenge"]:
                challenge_url = f"https://lichess.org/{response['challenge']['fullId']}"
                print(f"Challenge created: {challenge_url}")
                webbrowser.open(challenge_url)
            elif (
                "id" in response
            ):  # Fallback for older/different API response structure? Check Lichess docs.
                challenge_url = f"https://lichess.org/{response['id']}"
                print(f"Challenge created (using ID): {challenge_url}")
                webbrowser.open(challenge_url)
            else:
                print(f"Error creating challenge: {response.get('error', response)}")
                continue

        except requests.exceptions.RequestException as e:
            print(f"Network error creating challenge: {e}")
            continue
        except Exception as e:
            print(f"Error creating challenge: {e}")
            continue

        while True:
            result_input = (
                input(
                    "Game complete! Enter your result (w=win, d=draw, l=loss, q=quit): "
                )
                .lower()
                .strip()
            )
            if result_input == "w":
                tally["wins"] += 1
                break
            elif result_input == "d":
                tally["draws"] += 1
                break
            elif result_input == "l":
                tally["losses"] += 1
                break
            elif result_input == "q":
                print("Quitting practice session.")
                return  # Exit the function cleanly
            else:
                print("Invalid input. Please enter w, d, l, or q.")
        if result_input == "q":  # Need to check again to break outer loop
            break


def find_cql_positions(pgn_file):
    """
    Finds positions in a PGN file that are marked with '{CQL}' in comments
    AND have MAX_TABLEBASE_PIECES or fewer pieces on the board.
    """
    cql_positions = []
    game_count = 0
    print(
        f"Scanning PGN '{pgn_file}' for {{CQL}} comments in positions with <= {MAX_TABLEBASE_PIECES} pieces..."
    )
    try:
        # Re-open file to process games completely
        with open(pgn_file, encoding="latin-1") as pgn:
            while True:
                try:
                    game = chess.pgn.read_game(pgn)
                except Exception as read_error:
                    print(
                        f"  Warning: Skipping game due to parsing error: {read_error}"
                    )
                    # Attempt to find the next game header to potentially recover
                    headers = chess.pgn.read_headers(pgn)  # Try to skip to next game
                    if headers is None:
                        break  # EOF reached after error
                    continue  # Skip processing the errored game body

                if game is None:
                    break  # End of file

                game_count += 1
                node = game
                # move_number = 0  # <<< REMOVED THIS LINE (F841)
                ply_count = 0

                # Traverse the main line
                while node is not None:
                    # Check comments on the node *before* processing variations
                    if node.comment and "CQL" in node.comment:
                        board = node.board()
                        piece_count = len(board.piece_map())

                        if piece_count <= MAX_TABLEBASE_PIECES:
                            fen = board.fen()
                            to_move = "white" if board.turn == chess.WHITE else "black"
                            prev_move_san = "N/A"
                            if node.parent:
                                try:
                                    prev_board = node.parent.board()
                                    prev_move_san = prev_board.san(node.move)
                                except (
                                    ValueError
                                ):  # Be specific about expected error for SAN
                                    prev_move_san = node.uci()  # Fallback to UCI
                                except (
                                    Exception
                                ) as e_san:  # Catch other potential issues
                                    print(
                                        f"Warning: Could not get SAN for move {node.uci()} in game {game_count}: {e_san}"
                                    )
                                    prev_move_san = node.uci()

                            cql_positions.append(
                                {
                                    "fen": fen,
                                    "to_move": to_move,
                                    "game_info": f"Game {game_count}: {game.headers.get('White', '?')} vs {game.headers.get('Black', '?')}",
                                    "event": game.headers.get("Event", "Unknown"),
                                    "move_leading_to_pos": prev_move_san,
                                    "ply": ply_count,
                                }
                            )

                    # Move to the next node in the main line
                    if node.variations:
                        node = node.variations[0]
                        ply_count += 1
                    else:
                        node = None  # End of main line

    except FileNotFoundError:
        print(f"Error: PGN file not found at {pgn_file}")
        return []
    except Exception as e:
        print(f"Error reading PGN file structure: {e}")
        return []

    print(
        f"Finished scanning. Found {len(cql_positions)} potential tablebase positions."
    )
    return cql_positions


def challenge_from_endgame_positions(pgn_file, num_games, tally, aim="win"):  # noqa
    """
    Practice endgame positions found via find_cql_positions, verifying with tablebase.
    """
    # Find positions marked with CQL AND having <= MAX_TABLEBASE_PIECES pieces
    cql_positions = find_cql_positions(pgn_file)
    if not cql_positions:
        print("No suitable positions marked with {CQL} (and <= 7 pieces) found.")
        return

    target_positions = []
    print("Checking found positions with Lichess tablebase...")
    checked_count = 0
    for pos in cql_positions:
        checked_count += 1
        # FEN is already checked for piece count conceptually in find_cql_positions
        # but get_tablebase_result also does a check for safety.
        print(
            f"  Checking position {checked_count}/{len(cql_positions)} from {pos['game_info']}..."
        )
        result, best_move = get_tablebase_result(pos["fen"])

        if result is not None:
            # Check if the tablebase result matches the desired aim
            # Tablebase 'win' means it's winning for the player whose turn it is in the FEN
            # Tablebase 'loss' means it's losing for the player whose turn it is
            # Tablebase 'draw' is a draw regardless of whose turn it is (usually)
            current_player_wins = result == "win"
            current_player_draws = (
                result == "draw"
            )  # Includes blessed/cursed wins if API provides that detail

            match = False
            if aim == "win" and current_player_wins:
                match = True
            elif aim == "draw" and current_player_draws:
                match = True
            # Add handling for losing positions if needed (e.g., aim="defend")
            # elif aim == "defend" and result == "loss": # If you add a 'defend' aim
            #    match = True

            if match:
                pos["best_move"] = best_move if best_move else "N/A"
                pos["tablebase_result"] = result
                target_positions.append(pos)
                print(
                    f"    -> Added position. Aim '{aim}', TB result '{result}'. Best move: {pos['best_move']}"
                )
            else:
                print(
                    f"    -> Skipped position. Aim '{aim}', but TB result is '{result}'."
                )
        else:
            print(
                "    -> Skipped position. Tablebase lookup failed or position not in TB."
            )

    if not target_positions:
        print(f"No positions found matching aim '{aim}' after tablebase verification.")
        return

    print(f"\nFound {len(target_positions)} positions matching aim '{aim}'.")

    num_to_play = min(num_games, len(target_positions))
    if num_to_play <= 0:
        print("No games to play.")
        return

    selected_positions = random.sample(target_positions, num_to_play)
    print(f"Selected {num_to_play} positions for practice.")

    for i, pos in enumerate(selected_positions, 1):
        print(f"\n--- Position {i}/{num_to_play} ---")
        print(f"From: {pos['game_info']} (Event: {pos['event']})")
        print(
            f"Position after opponent's move: {pos['move_leading_to_pos']} (Ply: {pos['ply']})"
        )
        print(
            f"Your turn ({pos['to_move']}). Aim: {aim.capitalize()}. Tablebase says: {pos['tablebase_result']}"
        )
        # Only show best move if you want the 'cheat sheet'
        # print(f"Best tablebase move: {pos.get('best_move', 'N/A')}")
        print(f"FEN: {pos['fen']}")

        try:
            response = requests.post(
                "https://lichess.org/api/challenge/ai",
                headers={"Authorization": f"Bearer {api_key}"},
                data={
                    "level": 8,
                    "clock.limit": 60,  # More time for endgames
                    "clock.increment": 2,
                    "fen": pos["fen"],
                    "color": pos[
                        "to_move"
                    ],  # Play as the side whose turn it is in the FEN
                },
                timeout=10,  # Add a timeout
            ).json()

            # Check response structure carefully based on Lichess API docs
            if "challenge" in response and "fullId" in response["challenge"]:
                challenge_url = f"https://lichess.org/{response['challenge']['fullId']}"
                print(f"Challenge created: {challenge_url}")
                webbrowser.open(challenge_url)
            elif "id" in response:  # Fallback check
                challenge_url = f"https://lichess.org/{response['id']}"
                print(f"Challenge created (using ID): {challenge_url}")
                webbrowser.open(challenge_url)
            else:
                print(f"Error creating challenge: {response.get('error', response)}")
                continue  # Skip to next position

        except requests.exceptions.RequestException as e:
            print(f"Network error creating challenge: {e}")
            continue
        except Exception as e:
            print(f"Error creating challenge: {e}")
            continue

        # Get user input for result
        while True:
            result_input = (
                input(
                    "Game complete! Enter your result (w=win, d=draw, l=loss, q=quit): "
                )
                .lower()
                .strip()
            )
            if result_input == "w":
                tally["wins"] += 1
                # Optional: Check if win matches aim
                if aim == "win":
                    print("  > Correct result!")
                elif aim == "draw":
                    print("  > Aim was draw, but you won.")
                break
            elif result_input == "d":
                tally["draws"] += 1
                if aim == "draw":
                    print("  > Correct result!")
                elif aim == "win":
                    print("  > Aim was win, but you drew.")
                break
            elif result_input == "l":
                tally["losses"] += 1
                print(
                    "  > Incorrect result."
                )  # Loss is always incorrect if aim is win/draw
                break
            elif result_input == "q":
                print("Quitting practice session.")
                return  # Exit function
            else:
                print("Invalid input. Please enter w, d, l, or q.")
        if result_input == "q":  # Break outer loop if quit
            break


def generate_random_valid_position(white_piece_chars, black_piece_chars):
    """
    Generates a random, valid chess position with the specified pieces.
    Ensures kings exist, no pawns on back ranks, and the side NOT to move is not in check.
    Returns a valid chess.Board object or None if failed after attempts.
    """
    piece_map_from_char = {
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

    white_pieces = [piece_map_from_char[p] for p in white_piece_chars]
    black_pieces = [piece_map_from_char[p] for p in black_piece_chars]
    all_pieces = white_pieces + black_pieces

    if not white_pieces or not black_pieces:
        print("Error: Piece lists cannot be empty.")
        return None
    if (
        white_pieces[0].piece_type != chess.KING
        or black_pieces[0].piece_type != chess.KING
    ):
        # Assuming first piece is king based on typical input format
        print("Error: First piece for each side must be the King (K/k).")
        return None

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        board = chess.Board(fen=None)  # Start with an empty board
        squares = list(chess.SQUARES)
        random.shuffle(squares)

        try:
            current_squares = squares[: len(all_pieces)]
            if len(current_squares) < len(all_pieces):
                # Should not happen if len(SQUARES) >= len(all_pieces)
                continue

            temp_piece_map = {}
            valid_placement = True
            for i, piece in enumerate(all_pieces):
                square = current_squares[i]
                # Basic check: No pawns on rank 1 or 8
                if piece.piece_type == chess.PAWN:
                    if chess.square_rank(square) == 0 or chess.square_rank(square) == 7:
                        valid_placement = False
                        break
                temp_piece_map[square] = piece

            if not valid_placement:
                continue  # Retry placement

            board.set_piece_map(temp_piece_map)

            # Set turn randomly
            board.turn = random.choice([chess.WHITE, chess.BLACK])

            # Clear castling and en passant (unlikely relevant but safe)
            board.castling_rights = 0
            board.ep_square = None

            # --- CRUCIAL VALIDATION ---
            # 1. Basic board validity (catches some impossible setups)
            if not board.is_valid():
                # print(f"Debug Attempt {attempt}: Invalid board state (is_valid).")
                continue

            # 2. Check if the side *NOT* to move is in check (illegal position)
            board.push(chess.Move.null())  # Make a null move to switch turn temporarily
            if board.is_check():
                # print(f"Debug Attempt {attempt}: Side not to move is in check.")
                board.pop()  # Revert null move
                continue
            board.pop()  # Revert null move (if not in check)

            # 3. Ensure kings are sufficiently separated? (Optional, less strict)
            # k1_sq = board.king(chess.WHITE)
            # k2_sq = board.king(chess.BLACK)
            # if k1_sq is not None and k2_sq is not None and chess.square_distance(k1_sq, k2_sq) <= 1:
            #     continue # Kings too close

            # If all checks pass, we have a valid position
            # print(f"Debug Attempt {attempt}: Found valid position: {board.fen()}")
            return board

        except Exception:
            # Catch potential errors during placement/validation
            # print(f"Debug Attempt {attempt}: Exception during generation: {e}")
            continue  # Try next attempt

    print(
        f"Error: Failed to generate a valid position after {MAX_GENERATION_ATTEMPTS} attempts."
    )
    return None


# --- MODIFIED FUNCTION SIGNATURE ---
def challenge_from_random_endgame(
    white_pieces_str, black_pieces_str, num_games, tally, aim="win", play_color=None
):
    # --- END MODIFIED SIGNATURE ---
    """
    Generates random endgame positions with specified material, checks tablebase,
    and creates challenges for positions matching the aim, allowing user to specify play color.
    """
    print("\n--- Random Endgame Generation ---")
    # ...(print statements for pieces/aim remain the same)...
    if play_color:
        print(
            f"Attempting to find positions where YOU play as {play_color.capitalize()}."
        )
    else:
        print("Attempting to find positions matching aim (playing as side-to-move).")

    found_positions_count = 0
    generation_attempts = 0
    max_total_attempts = (
        MAX_GENERATION_ATTEMPTS * num_games * 5
    )  # Increase attempts slightly if color specified?
    if play_color:
        max_total_attempts *= 2  # Rough heuristic: might take longer

    while (
        found_positions_count < num_games and generation_attempts < max_total_attempts
    ):
        generation_attempts += 1
        # Give feedback more often if it's taking a while
        if generation_attempts % 10 == 0:
            print(f"Generation attempt {generation_attempts}...")

        # 1. Generate a valid random position
        board = generate_random_valid_position(white_pieces_str, black_pieces_str)
        if board is None:
            print("Stopping generation due to generator failure.")
            break

        fen = board.fen()
        generated_turn_color = "white" if board.turn == chess.WHITE else "black"

        # Print generated FEN less often to reduce noise, unless debugging
        # print(f"  Generated valid FEN: {fen} ({generated_turn_color} to move)")

        # 2. Check tablebase result
        result, best_move = get_tablebase_result(fen)
        # Print result less often unless debugging
        # print(f"  Tablebase result: {result} (for {generated_turn_color})")

        if result is None:
            # print("  Tablebase lookup failed or position not in TB. Trying again.") # Reduce noise
            time.sleep(0.5)
            continue

        # --- 3. ADJUSTED MATCHING LOGIC ---
        # Determine the color the user *will* play in the challenge
        challenge_color_for_user = play_color if play_color else generated_turn_color

        # Check if the position's outcome matches the user's aim *from the user's perspective*
        match = False
        if challenge_color_for_user == generated_turn_color:
            # User plays the side whose turn it is in the FEN
            # Result directly applies to the user
            if (aim == "win" and result == "win") or (
                aim == "draw" and result == "draw"
            ):
                match = True
        else:
            # User plays the side *opposite* to whose turn it is in the FEN
            # Result needs to be interpreted inversely for the user
            if (aim == "win" and result == "loss") or (
                aim == "draw" and result == "draw"
            ):  # Draw is draw for both
                match = True
                # If aim=win and result=loss, it means the FEN side-to-move loses, so user (playing other side) wins.

        # --- END ADJUSTED LOGIC ---

        if match:
            # Found a suitable position!
            print(f"\nAttempt {generation_attempts}: Found suitable position!")
            print(f"  FEN: {fen} ({generated_turn_color} to move)")
            print(f"  TB Result (for {generated_turn_color}): {result}")

            found_positions_count += 1

            # Calculate best_move_san if needed (already present)
            best_move_san = "N/A"
            if best_move:
                try:
                    move_obj = chess.Move.from_uci(best_move)
                    best_move_san = board.san(move_obj)
                except ValueError:
                    # print(f"  Warning: Could not get SAN for best move '{best_move}'. Using UCI.")
                    best_move_san = best_move

            # --- Update Print statements ---
            print(f"\n--- Practice Position {found_positions_count}/{num_games} ---")
            print(f"Material: {white_pieces_str} vs {black_pieces_str}")
            print(
                f"Challenge created for YOU to play as: {challenge_color_for_user.capitalize()}"
            )
            print(f"Your Aim: {aim.capitalize()}.")
            # Explain the TB result relative to the FEN position
            print(
                f"(Tablebase evaluates FEN position as '{result}' for {generated_turn_color})"
            )
            if best_move_san != "N/A":
                print(
                    f"Best Tablebase Move (for {generated_turn_color}): {best_move_san}"
                )
            print(f"FEN: {fen}")
            # --- End Update Print ---

            # --- 4. Create Lichess Challenge - Use correct color ---
            try:
                response = requests.post(
                    "https://lichess.org/api/challenge/ai",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data={
                        "level": 8,
                        "clock.limit": 60,  # Adjust time as needed
                        "clock.increment": 1,
                        "fen": fen,
                        "color": challenge_color_for_user,  # Play as the determined color
                    },
                    timeout=15,
                ).json()

                # ...(rest of challenge creation response handling is the same)...
                challenge_url = None
                if "challenge" in response and "fullId" in response["challenge"]:
                    challenge_url = (
                        f"https://lichess.org/{response['challenge']['fullId']}"
                    )
                elif "id" in response:
                    challenge_url = f"https://lichess.org/{response['id']}"

                if challenge_url:
                    print(f"Challenge created: {challenge_url}")
                    webbrowser.open(challenge_url)
                else:
                    print(
                        f"Error creating challenge: {response.get('error', response)}"
                    )
                    found_positions_count -= 1
                    print("Trying to find another position...")
                    continue

            # ...(exception handling for challenge creation is the same)...
            except requests.exceptions.RequestException as e:
                print(f"Network error creating challenge: {e}")
                found_positions_count -= 1
                print("Trying to find another position...")
                continue
            except Exception as e:
                print(f"Error creating challenge: {e}")
                found_positions_count -= 1
                print("Trying to find another position...")
                continue

            # --- 5. Get User Result Input ---
            # ...(this part remains the same)...
            while True:
                result_input = (
                    input(
                        "Game complete! Enter your result (w=win, d=draw, l=loss, q=quit): "
                    )
                    .lower()
                    .strip()
                )
                if result_input == "w":
                    tally["wins"] += 1
                    if aim == "win":
                        print("  > Correct result!")
                    elif aim == "draw":
                        print("  > Aim was draw, but you won.")
                    break
                elif result_input == "d":
                    tally["draws"] += 1
                    if aim == "draw":
                        print("  > Correct result!")
                    elif aim == "win":
                        print("  > Aim was win, but you drew.")
                    break
                elif result_input == "l":
                    tally["losses"] += 1
                    # Check if loss was expected (if aim was draw or loss?) - currently only win/draw aims
                    if aim == "win" or aim == "draw":
                        print("  > Incorrect result.")
                    break
                elif result_input == "q":
                    print("Quitting practice session.")
                    return  # Exit function
                else:
                    print("Invalid input. Please enter w, d, l, or q.")
            if result_input == "q":
                break  # Exit outer generation loop

        # else: # No match found, try again (reduce noise)
        # print(f"  Position FEN {fen} (TB:{result}) doesn't match aim '{aim}' for play_color '{play_color}'. Trying again.")
        # time.sleep(0.1) # Shorter delay maybe

    # ...(end of function summary print remains the same)...
    if found_positions_count < num_games:
        print(
            f"\nWarning: Only found {found_positions_count} out of {num_games} requested positions within attempt limits."
        )


def main_fn():
    parser = argparse.ArgumentParser(
        description="Chess practice tool with resigned games, PGN endgames, and random endgames."
    )
    parser.add_argument(
        "--pgn", help="Path to PGN file (required for 'resigned' and 'endgame' modes)"
    )
    parser.add_argument(
        "--mode",
        choices=["resigned", "endgame", "random_endgame"],
        required=True,
        help="Practice mode",
    )
    parser.add_argument(
        "--num", type=int, default=5, help="Number of positions to practice"
    )
    parser.add_argument(
        "--aim",
        choices=["win", "draw"],
        default="win",
        help="Aim for endgame/random_endgame modes (win/draw for the side to move)",
    )
    # Arguments specific to random_endgame mode
    parser.add_argument(
        "--white_pieces", help="White pieces for random_endgame (e.g., 'KQP')"
    )
    parser.add_argument(
        "--black_pieces", help="Black pieces for random_endgame (e.g., 'kr')"
    )
    # --- NEW ARGUMENT ---
    parser.add_argument(
        "--play_color",
        choices=["white", "black"],
        default=None,  # Default is None, meaning play as generated side-to-move
        help="Specify color YOU want to play as in random_endgame mode (optional)",
    )
    # --- END NEW ARGUMENT ---

    args = parser.parse_args()

    # --- Input Validation ---
    if args.mode in ["resigned", "endgame"] and not args.pgn:
        parser.error("--pgn is required for 'resigned' and 'endgame' modes.")
    if args.mode == "random_endgame" and (
        not args.white_pieces or not args.black_pieces
    ):
        parser.error(
            "--white_pieces and --black_pieces are required for 'random_endgame' mode."
        )
    if args.mode != "random_endgame" and args.play_color:
        parser.error("--play_color option is only valid for 'random_endgame' mode.")

    # Validate piece strings for random_endgame mode
    if args.mode == "random_endgame":
        # ...(existing piece validation remains the same)...
        wp = args.white_pieces
        bp = args.black_pieces
        valid_chars = "KQRBNPkqrbnp"
        if not all(c in valid_chars for c in wp) or not all(
            c in valid_chars for c in bp
        ):
            parser.error(
                "Invalid characters in piece strings. Use K,Q,R,B,N,P (uppercase for white, lowercase for black)."
            )
        if wp.count("K") != 1 or bp.count("k") != 1:
            parser.error("Exactly one King (K and k) must be specified for each side.")
        total_pieces = len(wp) + len(bp)
        if total_pieces > MAX_TABLEBASE_PIECES:
            parser.error(
                f"Total number of pieces ({total_pieces}) exceeds the tablebase limit ({MAX_TABLEBASE_PIECES})."
            )
        if not wp.startswith("K"):
            parser.error("White pieces string must start with 'K'.")
        if not bp.startswith("k"):
            parser.error("Black pieces string must start with 'k'.")

    # Simple validation for api_key
    # ...(existing api_key validation remains the same)...
    if not api_key or len(api_key) < 10:
        print("Error: Lichess API key not found or seems invalid in env.py.")
        print(
            "Please ensure env.py exists in the same directory and contains api_key = 'YOUR_LICHESS_API_TOKEN'"
        )
        return

    tally = {"wins": 0, "draws": 0, "losses": 0}

    print("--- Chess Practice Tool ---")
    print(f"Mode: {args.mode.replace('_', ' ').capitalize()}")
    if args.pgn:
        print(f"PGN File: {args.pgn}")
    print(f"Number of positions requested: {args.num}")
    if args.mode != "resigned":
        print(f"Aim: {args.aim.capitalize()}")
    if args.mode == "random_endgame":
        print(f"White Pieces: {args.white_pieces}")
        print(f"Black Pieces: {args.black_pieces}")
        if args.play_color:  # Print desired play color if specified
            print(f"Playing As: {args.play_color.capitalize()}")

    # --- Mode Dispatch ---
    if args.mode == "resigned":
        challenge_from_resigned_games(args.pgn, args.num, tally)
    elif args.mode == "endgame":
        challenge_from_endgame_positions(args.pgn, args.num, tally, aim=args.aim)
    elif args.mode == "random_endgame":
        # --- PASS play_color ARGUMENT ---
        challenge_from_random_endgame(
            args.white_pieces,
            args.black_pieces,
            args.num,
            tally,
            aim=args.aim,
            play_color=args.play_color,
        )
        # --- END PASS ---

    # ...(rest of the function remains the same)...
    print("\n--- Final Results ---")
    print(f"Wins: {tally['wins']}, Draws: {tally['draws']}, Losses: {tally['losses']}")
    total_played = tally["wins"] + tally["draws"] + tally["losses"]
    print(f"Total positions played: {total_played}")


if __name__ == "__main__":
    main_fn()
