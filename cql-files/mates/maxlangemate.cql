// Max Lange's mate: queen + bishop. Bishop defends the queen; queen
// is adjacent to the king and delivers the check. Geometrically very
// similar to Damiano's-bishop mate - the two are effectively the same
// motif under different names.

cql()

flipcolor {
    mate
    Q attacks k
    k attacks Q
    B attacks Q
}
