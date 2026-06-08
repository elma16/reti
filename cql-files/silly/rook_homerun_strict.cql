// Rook homerun (strict): a single rook reaches every corner -
// a1, h1, h8, a8 - on four consecutive turns of its own side.
// Only the opposing side's response separates the four corner moves;
// no other moves by the rook's own side may occur between them.

cql(quiet)

flipcolor {
    piece $r in R {
        line
          --> move from $r to a1
          --> .
          --> move from $r to h1
          --> .
          --> move from $r to h8
          --> .
          --> move from $r to a8
    }
}
