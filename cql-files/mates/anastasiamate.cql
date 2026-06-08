// Anastasia's mate: knight and rook team up to trap the opposing king
// against the edge of the board. The rook delivers the check (often
// from behind a friendly piece via x-ray); the knight covers the
// flight squares on the open side; exactly one own piece blocks the
// remaining flight on the same rank/file as the rook.

cql()

flipcolor {
    mate
    R attacks k
    N >= 1                                  // knight is part of the trap
    # (. attackedby k) == 5                 // king on the edge (not corner)
    # ([a] & . attackedby k) == 1           // exactly one friendly blocker
    # (R attacks (_ attackedby k)) >= 1     // rook covers at least one flight
    # (N attacks (_ attackedby k)) >= 1     // knight covers at least one flight
}
