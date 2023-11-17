/**********
Find positions where:
  in the variations black moves to pin a P by a q
  but in the mainline black cannot pin that pawn because the K
   - and only the K  - has moved.

The positions must arise from a white try.

The distance specification is used to guarantee that that variation
and the mainline are not too 'nearby': at least one of them must be
a distance of at least 4 from their latest common ancestor. This
eliminates certain uninteresting expressions of the theme.
***********/

cql( input hhdbvi.pgn variations)
  btm mainline ♛ ♙
  echo(source target){
     variation btm
     #◭==source:#◭
     ♔≠source:♔
     ~(source∩target)== ♔ ∪ source:♔

     /* in the variation (here), the q pins the P*/
     ⊢ primary ♛――
		  pinnedpawn=pin through ♙ from ♛
                  pinnedpawn //check this is not empty		  

    /* but in the mainline, this pin is not legal */
     source: not legal ♛――ray(♔ pinnedpawn □)
     L=lca(source target)
     L:wtm
     max(distance(source L)
         distance(target L))≥4
    source:///"The black queen cannot pin the P on " pinnedpawn
    child:///"The black queen pins the P on " pinnedpawn
  } 


 
 
