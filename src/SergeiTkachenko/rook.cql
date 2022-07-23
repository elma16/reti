cql()

;; Tkachenko 1
;; A position where the side which wins or draws has just a king and a pawn

((result 1-0 or result 1/2-1/2) and
(R == 1
 Q == 0
 P == 0
 N == 0
 B == 0)
)
or
((result 0-1 or result 1/2-1/2) and
(r == 1
 q == 0
 p == 0
 n == 0
 b == 0)
 )
