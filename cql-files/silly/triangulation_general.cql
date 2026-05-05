// Find triangulation by any piece (king, queen, rook, or bishop).
// Pawns can't move backwards, and knights always change square color
// in 3 moves -> they can never triangulate. So we restrict to K, Q, R, B.
//
// We use piece tracking (piece variables preserve a piece's identity across
// positions even when there are multiple pieces of the same type) to follow
// one specific piece through 3 moves.
//
// Pattern detected at the position right after the third move:
//   start_pos (P-5): piece on square A, side X to move
//   P-4..P-3:        side X plays piece A->B
//   P-2..P-1:        side X plays piece B->C
//   current  (P):    side X plays piece C->A   <- we are here

cql(quiet)

flipcolor {
    // Iterate over each white K/Q/R/B currently on the board
    piece $p in [KQRB] {

        // $p is on the board at parent and at current, and just moved
        $A = $p                          // current square (must equal start)
        $C = parent:$p                   // square before last move
        $A & .                           // piece exists now
        $C & .                           // piece existed at parent
        $A != $C                         // last move actually moved $p

        // The previous "white to move" turn (3 plies back)
        $B = parent:parent:parent:$p
        $B & .                           // piece existed then
        $B != $C                         // moved between B-turn and C-turn

        // Position 5 plies ago: where triangulation began
        $start_pos = parent:parent:parent:parent:parent
        $start_pos:$p == $A              // piece was on the same square A then

        // Three different squares -> a real triangle
        $A != $B

        // The starting position was the same side-to-move
        $start_pos:wtm

        // Piece must have been the same (non-pawn) type at start
        // (excludes a pawn promoting mid-pattern)
        // type values: 1=pawn, 2=knight, 3=bishop, 4=rook, 5=queen, 6=king
        $start_pos:type $p >= 3

        comment("Triangulation by " $p)
    }
}
