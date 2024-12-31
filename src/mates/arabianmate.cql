cql()
⬓{btm mate
R -> k
k -> R
N -> R
_ <- k == 2}


// Arabian mate.
//cql() mate flipcolor flipvertical {
  // Place the pieces in their relative positions.
  //kh8 R[h7,g8] Nf6
  // Both flight squares are empty and the king is checked by a lone piece.
  //_ attackedby k == 2 and A attacks k == 1
  // Some opposing piece made a capture from a square in the mating rook's
  // line, making way for the mating move.
  //line <-- Dest = R attacks k
  //     <-- Source = move from R
  //     <-- a & between(Source Dest) and move capture A
//}
