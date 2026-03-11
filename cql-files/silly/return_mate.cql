;; Return-to-start checkmates:
;; The mating move is made by a non-king, non-pawn piece that returns to its original square.
;; - Works for either color (flipcolor).
;; - Requires the piece to have left its start square earlier (start square empty just before mate).
;; BROKEN

cql(
  input "path/to/games.pgn"
  output "output/return-to-start-mates.pgn"
  quiet
)

flipcolor

[Aa]M = [QRNB] {
  Start = M              ;; remember original square of the mating piece
  line
    --> move from M      ;; piece leaves its start square at least once
    --> move {0,}        ;; any intervening play
    --> Start&~M         ;; start square currently not occupied by that piece
    --> move from M to Start mate
  comment("Return-to-start mate by " typename M " on " Start)
}
