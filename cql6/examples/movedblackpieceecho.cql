/*************
Pairs of positions with the source in the mainline and the target
in the variations. They differ only in that
a single black piece has moved. They are reached by a path from
their latest common ancestor that has at least 15 consecutive
identical moves. (A "Warning: truncating long comment" warning when running
this file can be ignored).
The output is sorted by the number of consecutive moves
************/

cql(input hhdbvi.pgn variations)
 mainline
 sort "consecutive identical moves"
  echo (source target){
   variation
   sidetomove==source:sidetomove
   mismatches= ~(source&target)
   #mismatches==2
   piece Mover=a&mismatches
   square all x in mismatches
     x==Mover and source:(x&_)
         or
     x&_ and source:(x==Mover)
   comment(Mover " moved from " source:Mover)
   consecutivemoves (source target)>=15
 }

 
 
