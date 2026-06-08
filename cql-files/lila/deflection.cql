// deflection - an opponent defender is forced away from a critical square

cql()
 flipcolor {wtm
  piece D in [qrbnp]
  piece T in [qrbnp]
  D  attacks  T
  move from A to D
  : not D  attacks  T}

