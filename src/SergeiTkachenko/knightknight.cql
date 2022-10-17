cql()

;; Tkachenko 1
;; A position where the side which wins or draws has just a king and a pawn

((result 1-0 or result 1/2-1/2) and
(P == 0
 Q == 0
 R == 0
 N == 2
 B == 0)
)
or
((result 0-1 or result 1/2-1/2) and
(p == 0
 q == 0
 r == 0
 n == 2
 b == 0)
 )
