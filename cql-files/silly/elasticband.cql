// Elastic band trap (sketch): a knight pinned by an enemy bishop against
// a friendly bishop, followed by a sequence of captures that exploit
// the pin.

cql()

flipcolor {
    piece $p in [bq] {
        pin from $p through N to B
        line
          --> move from N capture a
          --> move from $p capture B
          --> move from N capture $p
    }
}