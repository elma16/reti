// Bad knight:
// "A knight on the rim is dim". A knight on the a- or h-file has at
// most 4 squares it can hop to. We flag a rim knight as "bad" when at
// most one of those squares is both unoccupied by a friendly piece AND
// not attacked by an enemy pawn — i.e., the knight has nowhere useful
// or safe to land.

cql(quiet)

flipcolor {
    piece $n in N {
        $n & (N[a1-8] | N[h1-8])

        $attacks = [Aa_] attackedby $n
        $safe = $attacks & ~A & ~([Aa_] attackedby p)
        #$safe <= 1

        comment("Bad knight on rim: " $n " safe-moves=" $safe)
    }
}
