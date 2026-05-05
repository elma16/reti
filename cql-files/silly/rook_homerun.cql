// Rook homerun: a single rook visits all four corners in order
// a1, h1, h8, a8 (with arbitrary play between visits).

cql(quiet)

flipcolor {
    piece $r in R {
        line
          --> move from $r to a1
          --> move {0 200}
          --> move from $r to h1
          --> move {0 200}
          --> move from $r to h8
          --> move {0 200}
          --> move from $r to a8
    }
}
