// hangingPiece - an undefended opponent piece is captured

cql()
 flipcolor {wtm
  piece T in [qrbn]
  not [a]  attacks  T
  move capture T}

comment("hangingPiece")
