import webbrowser
import chess
import numpy as np
import requests


class EndgameTraining:
    def __init__(self, white, black, training_side='white',required_result='win'):
        self.white = white
        self.black = black
        self.training_side = training_side
        self.required_result = required_result

    def random_generate(self):
        '''
        Generate a training game by randomly making a position
        '''
        pieces = self.white.upper() + self.black.lower()
        pieces = [chess.Piece.from_symbol(x) for x in pieces]
        isvalid = False
        while isvalid == False:
            board = chess.Board(fen=None)
            squares = np.random.choice(64, len(pieces), replace=False)
            for idx in range(len(pieces)):
                board.set_piece_at(squares[idx], pieces[idx])
            if board.is_valid():
                r = requests.get('http://tablebase.lichess.ovh/standard?fen={}'.format(board.fen()))
                if r.json()['category'] == self.required_result:
                    isvalid = True
        webbrowser.open('https://lichess.org/editor/'+board.fen().replace(' ','_'))
    def game_generate(self):
        '''
        Generate a training game by cql
        '''
        pass
    def logical_generate(self):
        '''
        Generate a training game by randomly making a position from logical rules
        '''
        pass

