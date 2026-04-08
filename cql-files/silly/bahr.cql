
cql()

;; Bahr's rule: KPP vs KP rook pawn endgame
;; When all three conditions are met, the position favours the defender (draw).

;; Pure pawn endgame: no pieces
[QqRrBbNn] == 0

;; 3 pawns total
[Pp] == 3

flipcolor flipvertical {

    ;; Stronger side has 2 pawns, weaker side has 1
    P == 2
    p == 1

    ;; Exactly one passed pawn (the outside pawn)
    passedpawns == 1

    ;; Condition 1: both sides have rook pawns on the a-file
    ;; (flipvertical handles h-file mirror)
    ;; and the stronger side's rook pawn has not crossed the 4th rank
    Pa2-4
    pa2-7

    ;; Condition 2: the attacking king is adjacent to the passed pawn
    K attacks (P & passedpawns)

    ;; Condition 3: the defending king is in front of the passed pawn
    ;; or in front of the attacking king
    (k & (up 1 7 (P & passedpawns))) or (k & (up 1 7 K))
}
