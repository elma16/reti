// Searches for the R4r3 chess motif.
// mentioned in amateur to im

cql()

line quiet <-- {
    flipcolor flip {
        P[a2-7] == 1
        P[f-h2-7] == 3
        connectedpawns == 6
        p[f-h2-7] == 3
        R == 1
        r == 1
        [Aa] == 11
    }
} {3,}
