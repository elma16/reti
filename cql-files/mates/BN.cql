// Bishop-and-knight mate: K+B+N vs bare K. The bare king is forced to
// a corner of the same colour as the bishop and mated there.

cql()

flipcolor {
    mate
    [Aa] == 4                            // only the four pieces on board
    B == 1
    N == 1
    # (. attackedby k) == 3              // bare king in a corner
}
