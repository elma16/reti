cql()
;; Crosspin : A piece is pinned in two ways simultaneously: relative and absolute.
;; TODO loop over all pieces q,r,n,b,p 

flipcolor flip{
    piece zz = p
    (pin from [A] through zz to k) and (pin from [A] through zz to [qrnb])
    }