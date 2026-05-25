// fork - a piece attacks two or more opponent pieces simultaneously

cql()
 flipcolor {wtm
piece X in [NBRQP]
  move from X
  : X  attacks  [kqrbn] >= 2}

comment("fork")
