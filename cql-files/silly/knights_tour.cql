// Knight tour (approximate): one knight makes many moves over the
// course of the game (consecutive or interleaved). Sorted by move
// count by that knight.

cql(quiet)

flipcolor {
    piece $n in N {
        sort "knight tour length (moves)"
        line
          --> move from $n {6 63}
    }
}
