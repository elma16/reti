// dovetailMate - queen mates diagonally adjacent to king, escape squares blocked by own pieces

cql() mate flipcolor shift flip {
  Qg2 kg3 [a]f4 [a]h4
  _ attackedby k == 5 and A attacks (_ attackedby k) == 1
}

comment("dovetailMate")
