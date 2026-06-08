// Searches for the absolutepinmate chess motif.

cql()

flipcolor {
    pinningPieces = pin from A
    pinnedPieces = pin through a

    line --> pin from A
         --> {
                 wtm
                 mate
                 pin from A == pinningPieces
                 pin through a != pinnedPieces
             }
}

