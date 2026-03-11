/* 
checkmate with a piece ending on its starting square 

e.g Qd1 mate Nb1 mate 

TODO there must be a cleaner way of doing this where we can loop over all the pieces and associate a starting square with them.
*/

cql()

square StartSquare in a-h1 {
    initial A StartSquare
    //mate
    parent: move from A to StartSquare
    }
