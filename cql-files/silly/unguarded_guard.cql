// Unguarded guard:
// A line-check is parried by interposing a piece on a square that is
// not defended by any of the defender's other pieces — the "guard"
// itself is unguarded.
//
//   1. parent:check, not check       -> the played move resolved a check
//   2. piece $checker in [rbq]       -> the checker was a sliding piece (flipcolor symmetric)
//   3. parent:($checker attacks K)   -> $checker was attacking the white king at parent
//   4. $line = parent: between(...)  -> squares strictly between checker and king at parent
//   5. $block = $line minus squares attacked by white at current
//      (the interposed piece is not defended by any other white piece —
//       a piece never attacks its own square, so the blocker itself
//       does not appear as a defender)
//   6. parent: (move to $block)      -> the move played from parent landed on such a square

cql(quiet)

flipcolor {
    parent:check
    not check

    piece $checker in [rbq] {
        parent: ($checker attacks K)

        $line = parent: between($checker K)
        $block = $line & ~(. attackedby A)

        parent: (move to $block)

        comment("Unguarded guard: blocked check by " $checker " on " $block)
    }
}
