// Double-attacked mate: a mating move where some attacking piece sits
// on a square attacked by at least two opposing pieces (a piece walked
// into multiple attacks but still delivered mate).

cql()

flipcolor {
    mate
    piece $p in A {
        $dest = $p
        parent: (a attacks $dest) >= 2
    }
}
