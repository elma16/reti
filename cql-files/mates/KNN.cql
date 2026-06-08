// Two-knight endgame mate: K+N+N vs bare K. Cannot be forced in
// general, but mate positions exist with the bare king in a corner.

cql()

flipcolor {
    mate
    [Aa] == 4                            // only the four pieces on board
    N == 2
    # (. attackedby k) == 3              // bare king in a corner
}
