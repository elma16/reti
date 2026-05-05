// Elastic band trap (sketch): a knight pinned by an enemy bishop against
// a friendly bishop, followed by a sequence of captures that exploit
// the pin.

cql()

flipcolor {
    pin from b through N to B
    line
      --> move from N capture a
      --> move from b capture B
      --> move from N capture b
}
