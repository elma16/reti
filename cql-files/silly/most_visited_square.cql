// Most-visited square (per game).
//
// Sort games by the longest streak of moves that all touch the same
// square — ranks games where one square is the focal point of play.

cql(quiet)

sort "max same-square visits"
square $sq in [Aa_] {
    line --> (move to $sq or move from $sq) {3 200}
}
