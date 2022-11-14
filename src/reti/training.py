import webbrowser
import chess
import numpy as np

class EndgameTraining:
    def __init__(self, white, black):
        self.white = white
        self.black = black
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
