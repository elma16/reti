// Same-piece opening streak (CQL6)
// Finds games where one physical piece is moved more than N times in a row
// (counting consecutive moves by the same side) during the opening.

cql()

flipcolor

streak_threshold = 3     // "more than N" moves
opening_move_limit = 12  // opening window in full moves

piece Repeater in [Aa] {
  streak_threshold < sort "one-piece opening streak"
    {
      line singlecolor quiet
        --> (move from Repeater and movenumber <= opening_move_limit)+
    }
  comment("One piece moved more than N times in a row in the opening")
}
