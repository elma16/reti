// Connected passed pawns: at least two passed pawns of the same colour
// on adjacent files in the same position.
//
// passedpawns -> set of all passed-pawn squares (either colour).
// We keep the white ones (P &), expand each to its full file, shift one
// file left/right to get the "adjacency mask", then keep only those
// passed pawns whose file is adjacent to another passed white pawn.
// flipcolor handles the symmetric black case.

cql(quiet)

flipcolor {
    $wpass = P & passedpawns

    // Squares on a file that contains a white passed pawn.
    $files = $wpass | up 1 7 $wpass | down 1 7 $wpass

    // Squares on a file immediately adjacent to such a file.
    $adj = (left 1 $files) | (right 1 $files)

    // White passed pawns whose file is adjacent to another passed white pawn.
    $cpp = $wpass & $adj
    #$cpp >= 2

    comment("Connected passed pawns: " $cpp)
}
