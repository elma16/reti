/*************
This template can be used to find underpromotion studies:

Pairs of positions differing only in that a single white non-pawn
piece has changed in the source {in the mainline} and the target {in
the variation}. Thus, that piece
must have been promoted to a different piece in a variation.
The critical position must be white to move

*************/

cql( input hhdbvi.pgn variations)
mainline 
sort "Sum of distances to the LCA"
 echo (source target){
    source<target
    variation
    sidetomove == source:sidetomove
    Mismatch=~(source∩target)
    #Mismatch==1
    pieceid Mismatch==source:pieceid Mismatch
    L=lca(source target)
    L:wtm
    distance(source L) + distance (target L)≥10
}

 
 
