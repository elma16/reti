// Return-to-starting-square mate: the mating move puts a non-king,
// non-pawn piece back on the EXACT square it occupied in the initial
// position (same physical piece, not merely a piece of the same type).

cql()

flipcolor {
    initial
    piece $a1r = Ra1
    piece $h1r = Rh1
    piece $b1n = Nb1
    piece $g1n = Ng1
    piece $c1b = Bc1
    piece $f1b = Bf1
    piece $d1q = Qd1

    find {
        mate
        (move previous from $a1r to a1) or
        (move previous from $h1r to h1) or
        (move previous from $b1n to b1) or
        (move previous from $g1n to g1) or
        (move previous from $c1b to c1) or
        (move previous from $f1b to f1) or
        (move previous from $d1q to d1)
    }
}
