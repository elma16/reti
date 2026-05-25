// exposedKing - the opponent king lacks pawn shelter and is vulnerable to attack

cql()
 flipcolor {
  k[a-h]5-8
  not p  attacks  k
  check}

comment("exposedKing")
