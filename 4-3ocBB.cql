;; Opposite colour bishops

cql(input hhdbvi.pgn)

;; white light squared bishop and black dark squared bishop

(B[a2,a4,a6,a8,b1,b3,b5,b7,c2,c4,c6,c8,d1,d3,d5,d7,e2,e4,e6,e8,f1,f3,f5,f7,g2,g4,g6,g8,h1,h3,h5,h7] == 1 and
 B[a1,a3,a5,a7,b2,b4,b6,b8,c1,c3,c5,c7,d2,d4,d6,d8,e1,e3,e5,e7,f2,f4,f6,f8,g1,g3,g5,g7,h2,h4,h6,h8] == 0 and
 b[a1,a3,a5,a7,b2,b4,b6,b8,c1,c3,c5,c7,d2,d4,d6,d8,e1,e3,e5,e7,f2,f4,f6,f8,g1,g3,g5,g7,h2,h4,h6,h8] == 1 and
 b[a2,a4,a6,a8,b1,b3,b5,b7,c2,c4,c6,c8,d1,d3,d5,d7,e2,e4,e6,e8,f1,f3,f5,f7,g2,g4,g6,g8,h1,h3,h5,h7] == 0)

or
;; white dark squared bishop and black light squared bishop

(B[a1,a3,a5,a7,b2,b4,b6,b8,c1,c3,c5,c7,d2,d4,d6,d8,e1,e3,e5,e7,f2,f4,f6,f8,g1,g3,g5,g7,h2,h4,h6,h8] == 1 and
 B[a2,a4,a6,a8,b1,b3,b5,b7,c2,c4,c6,c8,d1,d3,d5,d7,e2,e4,e6,e8,f1,f3,f5,f7,g2,g4,g6,g8,h1,h3,h5,h7] == 0 and
 b[a2,a4,a6,a8,b1,b3,b5,b7,c2,c4,c6,c8,d1,d3,d5,d7,e2,e4,e6,e8,f1,f3,f5,f7,g2,g4,g6,g8,h1,h3,h5,h7] == 1 and
 b[a1,a3,a5,a7,b2,b4,b6,b8,c1,c3,c5,c7,d2,d4,d6,d8,e1,e3,e5,e7,f2,f4,f6,f8,g1,g3,g5,g7,h2,h4,h6,h8] == 0)

R == 0
r == 0
N == 0
n == 0
Q == 0
q == 0
