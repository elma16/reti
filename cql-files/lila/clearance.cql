// clearance - a piece moves off a line to allow a ray piece to use that line

cql()
 flipcolor {wtm
  piece V in [QRBNP]
  piece E in [QRB]
  ray orthogonal (E V) or ray diagonal (E V)
  move from V
  : not ray orthogonal (E V) and not ray diagonal (E V)}

