// Return-to-starting-square mate: the mating move puts a non-king,
// non-pawn piece back on its standard starting square.

cql()

flipcolor {
    mate
    (move from N to b1) or
    (move from N to g1) or
    (move from B to c1) or
    (move from B to f1) or
    (move from R to a1) or
    (move from R to h1) or
    (move from Q to d1)
}
