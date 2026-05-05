// Double check: at least two enemy pieces attack the side-to-move's king.

cql()

flipcolor {
    check
    (A attacks k) >= 2
}
