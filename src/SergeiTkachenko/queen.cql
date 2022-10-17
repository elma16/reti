cql()

;; Tkachenko 5
;; A position where the side which wins or draws has just a king and a pawn

((result 1-0 or result 1/2-1/2) and
(Q == 1
 P == 0
 R == 0
 N == 0
 B == 0)
)
or
((result 0-1 or result 1/2-1/2) and
(q == 1
 p == 0
 r == 0
 n == 0
 b == 0)
 )
