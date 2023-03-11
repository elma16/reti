/******
Stalemates where stalemated side has power at least 15, sorted by the power
********/

cql(input hhdbvi.pgn)
flipcolor 
{wtm
 stalemate
 sort "Material value of stalemated side" power A
     >=15
}



