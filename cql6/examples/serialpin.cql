/*serial pins: x1 pins x2 pins x3..., sorted by the number
  of pins in the chain.
*/

cql(input hhdbvi.pgn quiet)
piece Pinner in (pin from [Aa])&~pin
sort "Chain Length" {
 piece CurrentPinner=Pinner
 Length=1
 comment ("Pin chain: " CurrentPinner)
 loop{
   piece CurrentPinner= pin through . from CurrentPinner
   comment("pins " CurrentPinner)
   Length+=1
   }
 Length>=4
}