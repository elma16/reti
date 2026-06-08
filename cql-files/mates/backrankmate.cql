// Back-rank mate: a rook or queen checkmates the king along its back
// rank (1st or 8th rank), where the king is shut in by its own pieces
// (usually pawns) on the next rank.

cql()

flipcolor {
    mate
    k & a-h8                             // black king on rank 8
    [RQ] attacks k                       // rook or queen checks
    # ([a] & . attackedby k) >= 2        // at least 2 friendly blockers around king
}
