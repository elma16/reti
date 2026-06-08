// Fischer's hedgehog regrouping: King to h1, Rook to g1, then the g4 pawn push
// (a kingside pawn-storm setup). The three moves must occur in THIS ORDER at
// some point in the game, but NOT necessarily on consecutive moves.
//
// `. {*}` is the gap: `.` (all squares) matches any position, and `{*}` repeats
// it zero or more times, so any number of unrelated moves may fall between the
// key moves. (Plain `-->` between two moves would force them to be consecutive.)

cql()

flipcolor flip {
    line
        --> move from K to h1
        --> . {*}
        --> move from R to g1
        --> . {*}
        --> move from P to g4
}
