cql()

;; Tkachenko 1
;; A position where the side which wins or draws has just a king and a pawn

x = 7

((result 1-0 or result 1/2-1/2) and
(P == 1 and Q == 0 and R == 0 and N == 0 and B == 0 and max("movenumber" "x"))
)
or
((result 0-1 or result 1/2-1/2) and
(p == 1 and q == 0 and r == 0 and n == 0 and b == 0 and max("movenumber" "x"))
 )
