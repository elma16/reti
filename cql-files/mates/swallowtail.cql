// Swallowtail (Guéridon) mate: queen orthogonally adjacent to king,
// mate, with two friendly pieces blocking the king's diagonal flight
// squares. King is not on the edge (5 empty neighbours).

cql()

flipcolor {
    mate
    Q attacks k
    k attacks Q
    ray orthogonal (Q k)
    _ attackedby k == 5
    # ([a] & . attackedby k) == 2
}
