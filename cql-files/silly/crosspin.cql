// Searches for the crosspin chess motif.

cql()
// Crosspin: a piece is pinned in two ways simultaneously by two different
// attackers along two different rays - one absolute (to the king), one
// relative (to another valuable black piece).

flipcolor {
    piece zz in [qrnbp] {
        piece $w1 in [QRB] {
            pin from $w1 through zz to k
            piece $w2 in [QRB] {
                pin from $w2 through zz to [qrnb] & ~zz
                $w1 != $w2
            }
        }
    }
}
