// Tripled-pawn creations.
//
// A capture that brings a pawn to a file already holding two same-
// colour pawns (so the file now has three). The capturing pawn must
// have come from another file (otherwise no new pawn arrived).

cql(quiet)

flipcolor {
    (move from P capture [a] to a2-7 and Pa2-7 == 3) or
    (move from P capture [a] to b2-7 and Pb2-7 == 3) or
    (move from P capture [a] to c2-7 and Pc2-7 == 3) or
    (move from P capture [a] to d2-7 and Pd2-7 == 3) or
    (move from P capture [a] to e2-7 and Pe2-7 == 3) or
    (move from P capture [a] to f2-7 and Pf2-7 == 3) or
    (move from P capture [a] to g2-7 and Pg2-7 == 3) or
    (move from P capture [a] to h2-7 and Ph2-7 == 3)
}
