#!/usr/bin/env python3

import re
import subprocess
import glob
import chess
import os
import sys
import chess.pgn
import io
from cairosvg import svg2png
from PIL import Image, ImageDraw


def game_length_array(content):
    game_array = [int(x[:-2]) for x in re.findall(r"\d{1,3}\.\s", content)]
    end_move = []
    for i in range(len(game_array)):
        if game_array[i] == 1:
            end_move.append(game_array[i - 1])
    if len(game_array) > 0:
        end_move.append(game_array[-1])
    return end_move


def alt_num_games(content):
    results = re.findall(r'Result\s"', content)
    return len(results)


def load_pgn(path):
    with open(path, "r", encoding="iso-8859-15") as file:
        content = file.read()
    return content


def merge_pgns(path):
    """
    Given the directory with all the pgns in it, output a pgn with all the results in one file
    """
    dir = path + "/*.pgn"
    read_files = glob.glob(dir)
    with open("0all.pgn", "wb") as outfile:
        for f in read_files:
            with open(f, "rb") as infile:
                outfile.write(infile.read())


def fen2tex(tex_file_name, img_dir):
    # write tex file
    with open(tex_file_name, "w") as f:
        f.write(
            r"""\documentclass{article}
    \usepackage{graphicx}
    \usepackage[absolute,overlay]{textpos}
    \setlength{\TPHorizModule}{1mm}
    \setlength{\TPVertModule}{1mm}
    \date{}
    \title{Elliott's Games!}
    \begin{document}
    \maketitle
    \centering
    \begin{document}
    \begin{textblock}{50}(-5,0)
      \rotatebox{90}{\includegraphics[width=5cm]{example-image-a}}
    \includegraphics[width=25mm]{/Users/elliottmacneil/python/reti/data/animals/stoat1.jpg}
    \end{textblock}
    Today's set of puzzles are mostly taken from the 2021 Online London Chess League, and a couple from the 2000 Bundesliga in Germany.
    Once again, if you get stuck, ask one of the coaches to come and help! Write your solutions \textbf{in notation}. \n"""
        )
        for img in os.listdir(img_dir):
            # print full path of image
            img_path = os.path.join(img_dir, img)
            f.write(r"\includegraphics[width=6cm, height=6cm]{" + img_path + "}\n")
        f.write(r"""\end{document}""")

    print("tex file written!")

    # execute it in latex
    subprocess.call(["pdflatex", "test.tex"])

    # open the pdf file
    if sys.platform == "darwin":
        subprocess.call(("open", "test.pdf"))
    elif os.name == "nt":
        os.startfile("test.pdf")
    elif os.name == "posix":
        subprocess.call(("xdg-open", "test.pdf"))


def fen2png(fen_string, img_name):
    """
    Convert FEN string to PNG image
    E.g: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1
    """
    board = chess.Board(fen=fen_string)
    svg_board = chess.svg.board(
        board=board, orientation=board.turn, colors={"inner border": "#15781B80"}
    ).encode("UTF-8")

    png_image = svg2png(bytestring=svg_board)
    pil_image = Image.open(io.BytesIO(png_image))

    if board.turn == chess.WHITE:
        color = (255, 255, 255)
    else:
        color = (0, 0, 0)
    draw = ImageDraw.Draw(pil_image)
    coords = [(383, 0), (378, 13), (388, 13)]
    draw.polygon(coords, fill=color, outline=(128, 128, 128))

    pil_image.save(img_name)


def print_relevant_positions(path):
    """
    Given a path to a pgn file already processed by CQL6, print the relevant positions in the pgn file.
    """
    fen_list = []
    white_player = []
    black_player = []
    pgn = open(path, encoding="utf-8", errors="replace")
    with open(path, encoding="utf-8", errors="replace") as file:
        content = file.read()
    num_games = game_length_array(content)[0]
    print("number of games:", num_games)
    for igame in range(num_games):
        game = chess.pgn.read_game(pgn)
        board = game.board()
        for node in game.mainline():
            move = node.move
            comment = node.comment
            board.push(move)
            if comment == "CQL":
                fen_list.append(board.fen())
                white_player.append(game.headers["White"])
                black_player.append(game.headers["Black"])
                break
        else:
            continue
    return fen_list, white_player, black_player
