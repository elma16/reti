;; Max hanging pieces per game:
;; Sorts games by the largest number of hanging pieces in any single position.
;; A piece is considered hanging if it is attacked by the opponent and not defended by its own side.
;; Counts both sides’ hanging pieces in each position; keeps the maximum seen in the game.

cql(
  input "path/to/games.pgn"
  output "output/most-hanging2.pgn"
  quiet
)

flipcolor

MaxHang = 0
BestPly = 0

find all {
  HangingWhite = A attackedby a and not (A attackedby A)
  HangingBlack = a attackedby A and not (a attackedby a)
  Hanging = HangingWhite | HangingBlack
  Count = find count { s[element]. s&Hanging }
  MaxHang < Count
  MaxHang = Count
  BestPly = ply
}

sort "max hanging pieces in a position" MaxHang
comment("Max hanging pieces in one position: " MaxHang " at ply " BestPly)
