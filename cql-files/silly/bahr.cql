// Bahr's rule -- KPP vs KP rook-pawn endings the rule calls drawn.
//
// https://www.arves.org/arves/index.php/en/endgamestudies/theory/1570-the-flaw-in-bahr-s-rule
//
// Bahr's rule covers a pawn ending with two blocked rook pawns plus one extra
// "outside" passed pawn for the stronger side. The rule says the position is a
// DRAW (the defender holds) when all three conditions hold:
//
//   1. The stronger side's rook pawn has NOT crossed the half-way line, i.e. it
//      is no further than its own 4th rank. If it has, the stronger side wins.
//   2. The stronger side's king stands next to (is adjacent to) its passed pawn.
//   3. The defending king stands directly in front of the passed pawn, or
//      directly in front of the attacking king.
//
// The rule is only a guideline: F. Santelli's position 8/8/8/8/p3k3/P7/4KP2/8
// meets all three conditions yet is in fact won for the stronger side when the
// defender is to move (the John Crum manoeuvre) -- this is the "flaw" discussed
// in the ARVES article above. Because the rule itself says nothing about the
// side to move, this query matches the geometry regardless of whose turn it is,
// so the rare flawed positions are matched too.

cql()

// Pure pawn endgame: kings and pawns only, three pawns in total.
[QqRrBbNn] == 0
[Pp] == 3

// flipcolor    -> let either side be the stronger one. It mirrors ranks as well
//                 as colours, so "up" below reads as "down" for the black case.
// flipvertical -> let the rook pawns sit on the h-file as well as the a-file.
flipcolor flipvertical {

    // Material split: stronger side has two pawns, weaker side has one.
    P == 2
    p == 1

    // Exactly one passed pawn: the stronger side's outside pawn. With the weaker
    // side's only pawn blocked on the rook file, this passer must be White's.
    passedpawns == 1
    $passer = P & passedpawns

    // --- Condition 1 ------------------------------------------------------
    // Both sides have a rook pawn on the a-file (flipvertical mirrors the h-file
    // case). The stronger side's rook pawn is its ONLY a-file pawn and has not
    // crossed its 4th rank; requiring it to be the only one also forces the
    // passer to be a genuine outside pawn rather than a doubled rook pawn.
    Pa2-4
    #(P & a1-8) == 1
    pa2-7

    // --- Condition 2 ------------------------------------------------------
    // The attacking king is adjacent to its passed pawn.
    K attacks $passer

    // --- Condition 3 ------------------------------------------------------
    // The defending king is directly in front of the passed pawn, or directly
    // in front of the attacking king (same file, further up the board).
    (k & (up 1 7 $passer)) or (k & (up 1 7 K))

    comment("Bahr's rule: outside passer on " $passer)
}
