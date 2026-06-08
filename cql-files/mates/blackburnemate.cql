// Blackburne's mate: two bishops on different diagonals near the king
// plus a knight cutting off sideways escape, with the king near the
// edge of the board.

cql()

flipcolor {
    mate
    B == 2
    N >= 1
    B attacks k
    # (. attackedby k) <= 5              // king at the edge of the board
    square all x in _ attackedby k
        (B attacks x) or (N attacks x)
}
