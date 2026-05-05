// Material imbalance: positions where white and black total piece power
// differs by at least 2 (e.g., one side has an extra minor piece).

cql()

power [Aa] >= 1
abs(power A - power a) >= 2
