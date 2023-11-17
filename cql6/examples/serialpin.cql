/*serial pins: x1 pins x2 pins x3..., sorted by the number
  of pins in the chain.
*/

cql(input hhdbvi.pgn quiet)
◭Pinner∊(pin from ◭)∩~pin
 sort "Chain Length" {
  ◭CurrentPinner=Pinner
  Length=1
  ///"Pin chain: " CurrentPinner
  loop{
   ◭CurrentPinner= pin through ◭ from CurrentPinner
   ///"pins " CurrentPinner
   Length+=1
   }
 Length≥4
}