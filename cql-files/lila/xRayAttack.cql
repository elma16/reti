// xRayAttack - a piece attacks through another piece on the same line

cql()
 flipcolor {
  piece X in [QRB]
  piece Y in [qrbnp]
  piece Z in [qrbnp]
  ray orthogonal (X Y Z) or ray diagonal (X Y Z)
}

comment("xRayAttack")
