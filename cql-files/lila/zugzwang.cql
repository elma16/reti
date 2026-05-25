// zugzwang - any move the opponent makes worsens their position
// Note: true zugzwang detection requires engine evaluation.
// This approximation finds positions where the side to move has very few legal moves.

cql()
 flipcolor {btm
  move count legal <= 3
  not check}

comment("zugzwang")
