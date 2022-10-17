;; Opposite colour bishops

cql()

;; white light squared bishop and black dark squared bishop

(light B == 1 and
 dark B == 0 and
 dark b == 1 and
 light b == 0 and
 P[a-h6] == 2 and
 connectedpawns == 2 and 
 p == 0)

or

;; white dark squared bishop and black light squared bishop

(dark B == 1 and
 light B == 0 and
 light b == 1 and
 dark b == 0 and
 P == 0 and
 connectedpawns == 2 and 
 p[a-h3] == 2)

[Aa] == 6