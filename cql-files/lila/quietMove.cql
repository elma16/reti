// quietMove - a subtle move that is not a capture, check, or direct attack

cql()
 flipcolor {wtm
  move from [QRBNP]
  : not check
  : not move capture [Aa]
  : not A  attacks  [qrbn]}

comment("quietMove")
