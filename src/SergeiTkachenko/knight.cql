cql()

;; Tkachenko 2
;; A position where the side which wins or draws has just a king and a knight

((result 1-0 or result 1/2-1/2) and
(N == 1
 Q == 0
 R == 0
 P == 0
 B == 0)
)
or
((result 0-1 or result 1/2-1/2) and
(n == 1
 q == 0
 r == 0
 p == 0
 b == 0)
 )
