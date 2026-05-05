"""Position-evaluation backends and CSV schema for ``export_cql_positions``.

The point of the split:

- :mod:`reti.evaluation.backends` defines a small ``PositionEvaluator``
  interface so a Syzygy probe, a Stockfish search, or a routing dispatcher
  ("≤5 pieces → tablebase, else engine") can all be plugged in interchangeably.
- :mod:`reti.evaluation.csv_schema` owns the CSV column list, the
  ``EvaluationResult`` dataclass, and the row-builder helpers that turn an
  evaluated position into a CSV row.

The high-level orchestrator (parse PGN, evaluate, write rows, manage progress)
still lives in ``reti.export_cql_positions`` so test patches that target that
module's namespace continue to work.
"""

from reti.evaluation.backends import (
    PositionEvaluator,
    RoutingEvaluator,
    StockfishEvaluator,
    StockfishSession,
    TablebaseEvaluator,
    evaluate_with_tablebase,
    open_tablebase_from_directories,
)
from reti.evaluation.csv_schema import (
    CSV_COLUMNS,
    EvaluationResult,
    build_file_error_row,
    build_marker_row,
    build_parse_error_row,
    classify_side_to_move_wdl,
    classify_stockfish_winner,
    empty_row,
    prepare_output_csv,
)

__all__ = [
    "CSV_COLUMNS",
    "EvaluationResult",
    "PositionEvaluator",
    "RoutingEvaluator",
    "StockfishEvaluator",
    "StockfishSession",
    "TablebaseEvaluator",
    "build_file_error_row",
    "build_marker_row",
    "build_parse_error_row",
    "classify_side_to_move_wdl",
    "classify_stockfish_winner",
    "empty_row",
    "evaluate_with_tablebase",
    "open_tablebase_from_directories",
    "prepare_output_csv",
]
