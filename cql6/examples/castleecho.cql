/*******
Two positions differ only in that in one castling (to a particular side) is allowed
and in the other that kind of castling is not allowed.
*******/

cql(input hhdbvi.pgn variations )
move legal castle
echo(source target){
  sidetomove==source:sidetomove
  source&target==.
  {source:move legal o-o
    and not move legal o-o
   comment "o-o is not legal"
   source:comment "o-o is legal"}
  or
  {source:move legal o-o-o
   and not move legal o-o-o
   comment "o-o-o is not legal"
   source:comment "o-o-o is legal"}
}   

  
  


	

