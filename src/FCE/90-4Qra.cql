;; Queen vs. Rook and minor piece

cql()

(Q == 1 and R == 0 and B == 0 and N == 0 and q == 0 and r == 1 and b == 1 and n == 0) or
(Q == 1 and R == 0 and B == 0 and N == 0 and q == 0 and r == 1 and b == 0 and n == 1) or
(Q == 0 and R == 1 and B == 1 and N == 0 and q == 1 and r == 0 and b == 0 and n == 0) or
(Q == 0 and R == 1 and B == 0 and N == 1 and q == 1 and r == 0 and b == 0 and n == 0)
