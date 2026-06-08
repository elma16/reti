// Ladder (lawnmower) mate: two major pieces working together push the
// bare king to the edge of the board. One major delivers check on the
// edge; the other cuts off the adjacent rank or file.

cql()

flipcolor {
    mate
    # (. attackedby k) == 5              // king on the edge (not corner)
    [RQ] attacks k                       // a major piece checks
    # [RQ] >= 2                          // at least two majors on white's side
    _ attackedby k == 5                  // all 5 neighbours empty (bare king)
}
