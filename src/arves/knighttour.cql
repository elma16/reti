cql ()
initial
piece $knight in [Nn]
sort "number of visited squares"
  countsquares 20 64
    square $visited in any
      next* $knight on $visited