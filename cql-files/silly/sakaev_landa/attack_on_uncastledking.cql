// Attack on the uncastled king (Sakaev & Landa): the winning side checkmates
// an enemy king that never castled, early in the game -- the king is caught in
// the centre before it can get to safety.

cql()

flipcolor {
    result 1-0
    mate
    movenumber < 25

    // The mated side never castled anywhere in the game.
    //   find <--          searches the ancestors of the (mate) position;
    //   {btm move castle}  matches an ancestor where it is the loser's turn
    //                      (btm) and the move actually played there is a castle.
    // The braces are required: without them find would bind to btm alone and
    // "move castle" would leak out as a separate filter.
    not find <-- {btm move castle}
}
