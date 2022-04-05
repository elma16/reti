;; Queen vs. Rook (with or without pawns)

cql(input hhdbvi.pgn)

(Q == 1 and R == 0 and q == 0 and r == 1) or 
(Q == 0 and R == 1 and q == 1 and r == 0)

p >= 0
P >= 0

B == 0
b == 0
N == 0
n == 0

;; for without pawns
;; [Aa] == 4
