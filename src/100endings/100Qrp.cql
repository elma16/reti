;; ending 100 : Q vs R and rook's pawn

cql()

(Q == 1 and R == 0 and P == 0 and q == 0 and r == 1 and p[a2-7,h2-7] == 1) or 
(Q == 0 and R == 1 and P[a2-7,h2-7] == 1 and q == 1 and r == 0 and p == 0)

[Aa] == 5