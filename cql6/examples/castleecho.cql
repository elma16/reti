/*******
Two positions differ only in that in one castling (to a particular side) is allowed
and in the other that kind of castling is not allowed.
*******/

cql(input hhdbvi.pgn variations )
 legal ――(castle)
echo(source target){
  sidetomove==source:sidetomove
  source∩target==▦
  {source:legal ――(o-o)
   not legal ――(o-o)
   /// "o-o is not legal"
   source:/// "o-o is legal"
  }
  or
  {source:legal ――(o-o-o)
   not legal ――(o-o-o)
   /// "o-o-o is not legal"
   source:/// "o-o-o is legal"
  }
}   

  
  


	

