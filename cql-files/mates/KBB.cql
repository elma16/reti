// Two-bishop endgame mate: K+B+B vs bare K. Bishops on opposite colours
// drive the bare king to a corner.

cql()

flipcolor {
    mate
    [Aa] == 4                            // only the four pieces on board
    B == 2
    # (. attackedby k) == 3              // bare king in a corner
}
