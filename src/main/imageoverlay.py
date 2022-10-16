#!/usr/bin/env python3


'''
Overlay all the images representing games from a given pgn.

'''
import chess.pgn
import chess.svg
import sys
import os, shutil
import cv2
import cairosvg
import re

dir = 'svg-output'
dir_png = 'png-output'

for line in [dir,dir_png]:
    shutil.rmtree(line)
    os.mkdir(line)

pgn = open(sys.argv[1])

with open(sys.argv[1]) as f:
    content = str(f.readlines())

number_of_games = len(re.findall(r'Event ', content))
len_of_subgame = int(sys.argv[2])

def make_images():
    for idx in range(number_of_games):
        first_game = chess.pgn.read_game(pgn)
        board = first_game.board()
        game_list = list(first_game.mainline_moves())
        for move in range(len_of_subgame):
            board.push(game_list[move])
            svg = chess.svg.board(board)
        with open(f'{dir}/board-{idx}.svg','w') as fh:
            fh.write(svg)
            svg_name='{}/board-{}.svg'.format(dir,idx)
            png_name='{}/board-{}.png'.format(dir_png,idx)
            cairosvg.svg2png(url=svg_name,write_to=png_name)
    return 0

make_images()
images = []
for filename in os.listdir(dir_png):
    img = cv2.imread(os.path.join(dir_png,filename))
    images.append(img)

weighted_images = [x / number_of_games for x in images]
blended_image = sum(weighted_images)

bi_dir = 'blend.png'
cv2.imwrite(bi_dir, blended_image)
