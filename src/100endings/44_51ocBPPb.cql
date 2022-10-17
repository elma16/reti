;; Opposite colour bishops

cql()

;; white light squared bishop and black dark squared bishop

(light B == 1 and
 dark B == 0 and
 dark b == 1 and
 light b == 0 and
 P == 2 and
 isolatedpawns == 2 and 
 p == 0)

or

;; white dark squared bishop and black light squared bishop

(dark B == 1 and
 light B == 0 and
 light b == 1 and
 dark b == 0 and
 P == 0 and
 isolatedpawns == 2 and 
 p == 2)

[Aa] == 6