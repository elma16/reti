// Rook homerun (compact variant): a single rook visits three corners
// a1 -> h1 -> h8 with arbitrary play between visits.

cql(quiet)

flipcolor {
    piece $r in R {
        line
          --> move from $r to a1
          --> move {0 200}
          --> move from $r to h1
          --> move {0 200}
          --> move from $r to h8
    }
}
