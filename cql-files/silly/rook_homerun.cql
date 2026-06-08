// Rook homerun: a single rook visits all four corners in order
// a1, h1, h8, a8. Other pieces may move between visits, but the
// tracked rook itself stays on each corner until the next jump
// (no off-corner wandering between visits).

cql(quiet)

flipcolor {
    piece $r in R {
        line
          --> move from $r to a1
          --> move from ~$r {0 200}
          --> move from $r to h1
          --> move from ~$r {0 200}
          --> move from $r to h8
          --> move from ~$r {0 200}
          --> move from $r to a8
    }
}
