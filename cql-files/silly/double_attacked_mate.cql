// Double-attacked mate finder (CQL6)
// Finds mates where the mating move steps onto a square attacked at least twice by the opponent.
// Works for either color via flipcolor.
// BROKEN

cql(
  input "path/to/games.pgn"
  output "output/double-attacked-mates.pgn"
  quiet
)

flipcolor

[Aa]M = --(from)
move from M mate
AttackerCount = find count { X[element]. a->to }
AttackerCount >= 2
sort "double-attacked mate" AttackerCount
comment("Mating move walked into " AttackerCount " opponent attacks on " to)
