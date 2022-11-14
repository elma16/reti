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
        board = chess.Board()
        pieces = self.white + self.black
        pieces = [chess.Piece.from_symbol(x) for x in pieces]
        print(pieces)
        isvalid = False
        while isvalid == False:
            squares = np.random.choice(64, len(pieces), replace=False)
            for idx in range(len(pieces)):
                board.set_piece_at(squares[idx], pieces[idx])
            if board.is_valid():
                isvalid = True
                return board

        # fen of the board
        fen = board.fen()
        print(fen)
        webbrowser.open('https://lichess.org/editor/'+fen.replace(' ','_'))
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
    def tablebase_generate(self):
        '''
        Generate a training game by randomly making a position from tablebase
        '''
        pass

