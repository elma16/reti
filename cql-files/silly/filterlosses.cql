// Filter games whose Termination tag matches "Normal" (i.e., the game
// ended via mate/resignation/agreement rather than time forfeit or
// other unusual termination).

cql()

tag "Termination" ~~ "Normal"
