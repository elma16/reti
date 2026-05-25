// interference - a piece blocks the line between an opponent defender and the square it guards

cql()
 flipcolor {
  piece D in [qrb]
  piece T in [a]
  D  attacks  T
  move from [Aa] to between(D T)
  : not D  attacks  T
}

comment("interference")
