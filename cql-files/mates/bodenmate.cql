// Boden's mate: two bishops on criss-crossing diagonals deliver
// checkmate to a king whose flight squares are blocked by its own
// pieces (typically a rook plus a pawn).

cql()

flipcolor {
    mate
    B == 2
    B attacks k
    square all x in _ attackedby k
        B attacks x                      // every empty flight square attacked by a bishop
}
