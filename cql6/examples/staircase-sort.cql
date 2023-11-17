/*********
Find all queen staircases of either color of length
at least 8 and sort the output by the length of the staircase.

No gaps in the staircase are allowed. See staircase-sort-annotated.cql
for a version that allows gaps (and has better annotations).

The ✵ makes the staircase go in any direction The ✵
looks for both black and white queen staircases

   sort "staircase size""

just sorts the following path filter, and in the output it makes sure
that the annotations say the words "staircase size"

◎△
or focus A
means that only white moves are considered.

See the documentation for 'up' and 'right' for more discussion.

***********/

cql(input hhdbvi.pgn matchstring "")
✵⬓{
  8≤sort "staircase length"
   ⊢◎△ nestban
   (♕――up 1 ♕ 
    ♕――right 1 ♕)+
    ♕――up 1 ♕ ? 
}


