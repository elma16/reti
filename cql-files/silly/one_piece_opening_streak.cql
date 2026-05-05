// Same-piece opening streak: a single piece is moved multiple times
// in a row by its side during the opening (first 12 full moves).

cql(quiet)

piece $Repeater in [Aa] {
    sort "one-piece opening streak"
    line singlecolor
      --> (move from $Repeater and movenumber <= 12) {3 12}
}
