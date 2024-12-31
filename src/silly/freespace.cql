/*********************
print the amount of freespace around the king at each turn.
**********************/


cql()

freespaceWhite = {#_ attackedby K}
freespaceBlack = {#_ attackedby k}

comment ("w:" freespaceWhite "b:" freespaceBlack)
 
