// Rook (box) mate: K+R vs bare K. The bare king is driven to the
// edge of the board, rook delivers check from rank or file, and the
// supporting friendly king (not a bishop!) covers the flight squares.

cql()

flipcolor {
    mate
    R attacks k
    [Aa] == 3                            // K + R + k only (no other material)
    # (. attackedby k) <= 5              // bare king on edge or in corner
    square all x in _ attackedby k
        (R attacks x) or (K attacks x)
}
