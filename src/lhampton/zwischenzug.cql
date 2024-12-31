// Zwischenzug.
cql() flipcolor {
  sort min "Line length"
  line
    --> // A capture that is not by a pawn and is not a recapture.
        {
        Square =? move capture a from ~P
        not move capture Square previous
        PowerDiff = power A - power a
        }
    --> // The recapture is delayed at least one move.
        {
        // The next move is not a recapture.
        not check and move to ~Square
        // Assign the [attacked] piece that is to be recaptured.
        piece Piece = Square attackedby a
        // That piece has fewer guards than attackers.
        #(Square attackedby a) > #(Square attackedby A)
        }
    --> not move from Piece {1 5}
    --> // The piece is eventually recaptured...
        move to Square capture Piece
    --> // ... resulting in material gain.
        PowerDiff > power A - power a and not move capture .
}