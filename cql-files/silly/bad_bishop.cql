// Bad bishop:
// A side has a bishop on a colour complex (light or dark squares) where
// many of its own pawns sit, restricting the bishop's mobility.
// Heuristic: the side has at least 4 pawns on the bishop's colour AND
// at least 2 more there than on the opposite colour.

cql(quiet)

flipcolor {
    {
        #(light B) >= 1
        #(light P) >= 4
        #(light P) >= #(dark P) + 2
        comment("Bad light-squared bishop: " #(light P) " light vs " #(dark P) " dark pawns")
    }
    or
    {
        #(dark B) >= 1
        #(dark P) >= 4
        #(dark P) >= #(light P) + 2
        comment("Bad dark-squared bishop: " #(dark P) " dark vs " #(light P) " light pawns")
    }
}
