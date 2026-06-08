// Triangle mate: queen, rook, and king form a triangle. The queen is
// adjacent to the king and delivers the mate; the rook supports the
// queen from the queen's own file or rank (so the three pieces are
// non-collinear, hence the triangle).

cql()

flipcolor {
    mate
    Q attacks k
    k attacks Q
    R attacks Q
    ray orthogonal (R Q)
    A attacks k == Q
}
