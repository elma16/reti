// Searches for the suffocationmate checkmate pattern.




cql()
flipcolor{
mate
N  attacks  k
_  attackedby  k == 2

square all x in _  attackedby  k
       B  attacks  x
       }


//cql() mate flipcolor shift flip {
//   Ne7 Bc3 kg8
//}

