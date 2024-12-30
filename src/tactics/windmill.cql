// copyright Lionel Hampton

cql()
ply > 40
flipcolor
// Iterate over the windmilling pieces.
piece Mill in [RBN]
// Iterate over the stationary pieces giving discovery.
piece Disc in [RB] {
      Disc != Mill
      sort "Line length"
      line singlecolor
        --> (Mill attacks k and move from k
        --> Disc attacks k and move from k and move from Mill capture . previous)}
