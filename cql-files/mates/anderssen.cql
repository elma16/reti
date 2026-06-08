// Anderssen's mate: a rook or queen checkmates the opposing king along
// the back rank (8th rank for white attacker), supported by a
// diagonally attacking piece - typically a pawn or bishop.

cql()

flipcolor {
    mate
    k & a-h8                             // black king on rank 8
    [RQ] attacks k                       // rook or queen checks
    k attacks [RQ]                       // attacker adjacent to king
    [PB] attacks [RQ]                    // pawn or bishop supports
}
