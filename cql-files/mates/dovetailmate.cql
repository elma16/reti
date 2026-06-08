// Dovetail (Cozio's) mate: queen diagonally adjacent to king, mate,
// with two friendly pieces blocking the king's orthogonal flight
// squares. King is not on the edge (5 empty neighbours).

cql()

flipcolor {
    mate
    Q attacks k
    k attacks Q
    ray diagonal (Q k)
    _ attackedby k == 5
    # ([a] & . attackedby k) == 2
}
