/* 
How does the value of the knight go down when the knight steps into the corner?
*/

cql()
;; quite a lot of them are the knight taking something, so what if that square were empty?
flip flipcolor (move from N to a1) and (move from N to _)


;; what about the "dumb square"?
;;flip flipcolor move from N to b2
