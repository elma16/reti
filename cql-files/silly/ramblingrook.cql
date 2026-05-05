// Rambling rook: stalemate where the previous move was a black piece
// capturing a white rook (the rook had wandered into the wrong place).

cql()

flipcolor {
    stalemate
    parent: { move from a to R }
}
