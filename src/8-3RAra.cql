;; Rook and minor piece vs. Rook and minor piece

cql(input hhdbvi.pgn)

(R == 1 and B == 1 and N == 0 and r == 1 and b == 1 and n == 0) or
(R == 1 and B == 1 and N == 0 and r == 1 and b == 0 and n == 1) or
(R == 1 and B == 0 and N == 1 and r == 1 and b == 1 and n == 0) or
(R == 1 and B == 0 and N == 1 and r == 1 and b == 0 and n == 1)

Q == 0
q == 0

;; without pawns
;; P == 0
;; p == 0
