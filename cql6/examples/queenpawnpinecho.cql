/**********
Find positions where:
  in the variations black moves to pin a P by a q
  but in the mainline black cannot pin that pawn because the K
   - and only the K  - has moved.

The distance specification is used to guarantee that that variation
and the mainline are not too 'nearby': at least one of them must be
a distance of at least 4 from their latest common ancestor. This
eliminates certain uninteresting expressions of the theme.
***********/

cql( input hhdbvi.pgn variations)
  btm mainline q P
  PawnsBlackCouldPinInTheMainline=
    square z in P
          move legal from q to ray (K z _ )
   
  echo(source target){
     variation
     btm
     #[Aa]==source:#[Aa]
     K!=source:K
     ~(source&target)== K | source:K
     move primary from q               
     pinnedpawn=?child:pin through P from q
     source: not move legal from q to
              ray(K pinnedpawn _)
     L=lca(source target)
     max(distance(source L)
         distance(target L))>=4
    source:comment ("The black queen cannot pin the P on " pinnedpawn)
    child:comment("The black queen pins the P on " pinnedpawn)
  } 


 
 
