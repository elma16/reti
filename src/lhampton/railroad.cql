// Railroaded.
cql() flipcolor rotate90 { result 1-0
  sort "Line length"
  line  // Walk the king up between the tracks.
    --> (check and move from k to vertical between(Q R)
      --> // Alternate between rook and queen moves.
          move from R to diagonal 2 Q    or
          move from Q to horizontal 2 R) {3 100}
}