
//own implementation
//cql()
//btm mate
//R -> k
//_ <- k == 4
//square all x in _ <- k
//       (R -> x) or (N -> x)


// Anastasia's mate.
// The rotate90 transform matches the pattern on all four edges.
cql() mate flipcolor rotate90 {
  // Place the king and pawn in their relative positions.
  ka-h8  p & (down 1 k)
  // Establish that the king is attacked by a rook and by no other piece.
  R attacks k and A attacks k == 1
  // Only the knight guards the two empty escape squares.
  {square Guarded in (_ attackedby (N & down 3 k) & _ attackedby k)
      A attacks Guarded == 1} == 2
}
