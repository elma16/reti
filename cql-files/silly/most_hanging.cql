// Most hanging pieces in a single position.
//
// A piece is "hanging" if it is attacked by the opponent and not
// defended by any of its own side's pieces. We count hanging pieces
// of either colour in each position, then sort games by the largest
// count seen anywhere in the game.
//
// The 'sort' filter:
//   - sorts matching games by the best (max) value of its target
//   - smart-comments keep the per-game comment only for the peak position

cql(quiet)

sort "max hanging pieces" {
    // Squares of white pieces attacked by black, not defended by white
    $hang_white = (A attackedby a) & ~(A attackedby A)
    // Squares of black pieces attacked by white, not defended by black
    $hang_black = (a attackedby A) & ~(a attackedby a)
    // Union of both sides' hanging pieces
    $hanging = $hang_white | $hang_black
    $count = #$hanging

    // Only games with at least one hanging piece in some position
    $count >= 1

    comment("Hanging (" $count "): " $hanging)
    $count
}
