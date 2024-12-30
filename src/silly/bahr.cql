
cql()

⬓(P == 2 and p == 1)

[Aa = 5]

passedpawns == 1

;; condition 1. the rook's pawn is not past the halfway line.

(Pa2-7 and pa2-7) or (Ph2-7 and ph2-7)

;; condition 2. the attacking king is adjacent to the pawn.

(K->P and ray right (K P)) or (k->p and ray right (k p))

;; condition 3. the defending king is either in front of the pawn or in front of the king
;;((ray vertical (K k) or (ray vertical (K p) or (ray vertical (k P))

ray vertical (K k) or ray vertical (K p) or ray vertical (k P)
