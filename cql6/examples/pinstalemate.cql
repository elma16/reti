/*************
Find stalemates where at least two pieces are pinned.
Sort by the number of pins in descending order, and the total power of the
pieces in ascending order
************/

cql(input hhdbvi.pgn)
⬓{
 btm
 stalemate
 sort "number of pins"
     pin through ▲
       >1
 sort min "material" power ◭
 }
 
