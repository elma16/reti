// capturingDefender - a defender is captured, leaving the piece it protected vulnerable

cql()
 flipcolor {wtm
  piece D in [qrbnp]
  piece T in [qrbnp]
  D  attacks  T
  move capture D
  : not [a]  attacks  T}
