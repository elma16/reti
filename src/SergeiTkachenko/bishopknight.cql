cql()

;; Tkachenko 7
;; A position where the side which wins or draws has just a king and a pawn

((result 1-0 or result 1/2-1/2) and
(B == 1
 Q == 0
 R == 0
 N == 1
 P == 0)
)
or
((result 0-1 or result 1/2-1/2) and
(b == 1
 q == 0
 r == 0
 n == 1
 p == 0)
 )
