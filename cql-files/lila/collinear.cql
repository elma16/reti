// collinear - a ray piece moves along the same line as an opponent ray piece

cql()
 flipcolor {wtm
  piece X in [QRB]
  piece Y in [qrb]
  ray orthogonal (X Y) or ray diagonal (X Y)
  move from X
  : ray orthogonal (X Y) or ray diagonal (X Y)}

comment("collinear")
