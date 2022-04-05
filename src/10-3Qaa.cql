;; Queen vs. two minor pieces

cql(input hhdbvi.pgn)

(Q == 1 and B == 0 and N == 0 and q == 0 and b == 2 and n == 0) or
(Q == 1 and B == 0 and N == 0 and q == 0 and b == 1 and n == 1) or
(Q == 1 and B == 0 and N == 0 and q == 0 and b == 0 and n == 2) or
(Q == 0 and B == 2 and N == 0 and q == 1 and b == 0 and n == 0) or
(Q == 0 and B == 1 and N == 1 and q == 1 and b == 0 and n == 0) or
(Q == 0 and B == 0 and N == 2 and q == 1 and b == 0 and n == 0)


p >= 0
P >= 0

R == 0
r == 0
