;; Queen vs. three minor pieces

cql()

(Q == 1 and N == 0 and B == 0 and q == 0 and b == 0 and n == 3) or 
(Q == 1 and N == 0 and B == 0 and q == 0 and b == 1 and n == 2) or 
(Q == 1 and N == 0 and B == 0 and q == 0 and b == 2 and n == 1) or 
(Q == 1 and N == 0 and B == 0 and q == 0 and b == 3 and n == 0) or 
(q == 1 and n == 0 and b == 0 and Q == 0 and B == 0 and N == 3) or 
(q == 1 and n == 0 and b == 0 and Q == 0 and B == 1 and N == 2) or 
(q == 1 and n == 0 and b == 0 and Q == 0 and B == 2 and N == 1) or 
(q == 1 and n == 0 and b == 0 and Q == 0 and B == 3 and N == 0)

R == 0
r == 0
