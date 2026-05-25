// trappedPiece - a non-pawn opponent piece is captured after being trapped with no safe escape

cql()
 flipcolor {wtm
  piece T in [qrbn]
  A  attacks  T
  move legal from T == 0
  move capture T}

comment("trappedPiece")
