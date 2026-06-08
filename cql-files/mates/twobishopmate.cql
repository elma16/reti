// Two-bishop mate: K+B+B vs bare K. Both bishops (on opposite colours)
// drive the bare king to a corner. The bishop pair plus supporting king
// cover every flight square.

cql()

flipcolor {
    mate
    [Aa] == 4                            // K + B + B + k only
    B == 2
    B attacks k
    # (. attackedby k) == 3              // bare king in a corner
    square all x in _ attackedby k
        (B attacks x) or (K attacks x)
}
