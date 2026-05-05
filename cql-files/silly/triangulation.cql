// Find king triangulation patterns.
//
// A triangulation is a king maneuver where the king moves to 3 different
// squares forming a triangle and returns to its starting square.
// Pattern: K@A -> K@B -> K@C -> K@A (3 king moves, A != B != C)
//
// We detect this at the position right after the third king move.
// At that position, going back through the parent chain:
//   current (P):    K@A, just after K_C->A
//   parent (P-1):   K@C, side-that-triangulated about to play K_C->A
//   parent^3 (P-3): K@B, same side about to play K_B->C
//   parent^5 (P-5): K@A, same side about to play K_A->B  [START]

cql(quiet)

flipcolor {
    // The previous move must have been a (white) king move.
    // 'previous' makes K evaluate at the parent position, so this checks
    // the move's from-square was where the white king stood before moving.
    move previous from K

    // King's three squares
    $A = K                                       // current king square (= start of triangle)
    $C = parent:K                                // king square before last move
    $B = parent:parent:parent:K                  // king square at the white turn before that
    $start_pos = parent:parent:parent:parent:parent  // 5 plies ago: where it all began

    // King was on the same square 5 plies ago, with same side (white) to move
    $start_pos:K == $A
    $start_pos:wtm

    // The three squares form a real triangle (all different)
    $A != $B
    $A != $C
    $B != $C

    comment "King triangulation"
}
