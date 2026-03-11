
/*
Troitsky line - identifies positions where black pawns are behind the winning line
for two minor pieces versus pawn endgames, as defined by Troitsky.

TODO add the condition that the knight blockades the square in front of the pawn.
*/
cql()

; Ensure exactly 5 pieces on board
[Aa] == 5


; Check for pawns behind the line using alternating ranks
reversecolor {
    wtm
    N == 2 and (
    p[a4-7] or
    p[h4-7] or
    p[b6-7] or
    p[g6-7] or
    p[c5-7] or
    p[f5-7] or
    p[d4-7] or
    p[e4-7])
}
