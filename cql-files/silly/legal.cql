// Searches for the legal chess motif.

cql()
flipcolor flip{
line quiet
  --> move from n capture [A]d5
  --> move from B capture qd8
  --> move bb4}

comment("legal")
