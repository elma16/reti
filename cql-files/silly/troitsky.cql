// Troitsky line — positions where black pawns are behind the winning
// line for the two-knights-vs-pawn endgame, as defined by Troitsky.
//
// TODO: add the condition that the knight blockades the square in
// front of the pawn.

cql()

// Exactly 5 pieces on board (2 kings + 2 knights + 1 pawn)
[Aa] == 5

flipcolor {
    wtm
    N == 2
    (p[a4-7] or
     p[h4-7] or
     p[b6-7] or
     p[g6-7] or
     p[c5-7] or
     p[f5-7] or
     p[d4-7] or
     p[e4-7])
}
