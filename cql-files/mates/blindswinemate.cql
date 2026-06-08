// Blind-swine mate: doubled rooks on the seventh rank deliver
// checkmate to a king on the back rank. The name (Janowski) refers
// to two connected rooks on the opponent's 7th.

cql()

flipcolor {
    mate
    k & a-h8                             // black king on rank 8
    R[a-h7] == 2                         // both white rooks on rank 7
    R attacks k                          // a rook delivers check
}
