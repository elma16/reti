cql()

;; Tkachenko 6
;; A position where the side which wins or draws has just a king and a pawn

((result 1/2-1/2) and
(P == 0 and Q == 0 and R == 0 and N == 0 and B == 0)
)
or
((result 1/2-1/2) and
(p == 0 and q == 0 and r == 0 and n == 0 and b == 0)
 )
