;; Most-visited square (CQL6)
;; Counts visits (to or from) for every square in a game and ranks by the max.

cql(
  input "path/to/games.pgn"
  output "output/most-visited-squares.pgn"
  quiet
)

flipcolor

MaxVisits = 0
BestSquare = a1

find all {
  V[element].
  Visits = find count { move to V } + find count { move from V }
  MaxVisits < Visits
  MaxVisits = Visits
  BestSquare = V
}

sort "max square visits" MaxVisits
comment("Most-visited square: " BestSquare " visited " MaxVisits " times")
