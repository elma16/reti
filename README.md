# reti
A collection of cql scripts for endgame studies in pgn files.

## Introduction

In Müller and Lamprecht's celebrated work "Fundamental Chess Endgames", [they show a table on page 11 (this is from the Amazon website free sample of the book)](https://www.amazon.co.uk/Fundamental-Chess-Endings-One-Encyclopaedia/dp/1901983536?asin=B00BJ64LMW&revisionId=e8148266&format=1&depth=1). In it, they mention the use of Mega Database 2001, a proprietary database by Chessbase. Obtaining a copy of this to reproduce their table would be ~£100. It's now 2022, and open source chess has come a long way, and now it is trivial to obtain databases 100 times larger than this, completely for free. Namely, Lichess has an [open source database of games played on their website](https://database.lichess.org/#standard_games). The final piece of the puzzle is finding a way to obtain the required values. For this I used Gady Costeff's [CQL : Chess Query Language](http://www.gadycosteff.com/cql/). The result is a collection of scripts which can be run to analyse how often an ending occurs.

## But wait, there's more!

This analysis is not limited to just some big database, this can be done on _any_ pgn file you have available to you!

## Installation

To install, simply clone the repository

``` shell
gh repo clone elma16/reti
```

you will also need cql.

## Usage 

``` shell
source FCE-table.sh path/to/cql/executable path/to/database.pgn path/to/output/folder halfmoves
```

TODOs

- [ ] use cql to make a collection of endings, create a pgn with a bunch of them
  - [ ] randomly select a game from the pgn without replacement. 
  - [ ] if the ending is a theoretical win, play against the computer with the winning side
  - [ ] if the ending is a theoretical draw, you need to work out with which side you're defending.


python chess_practice.py --pgn your_endgames.pgn --mode endgame --num 5



# CQL Endgame Analyzer - Web Interface

A Flask web application that analyzes PGN files against 100 classical endgame patterns using CQL (Chess Query Language).

## Features

- 🎯 **Upload PGN Files** - Simple drag-and-drop or click to upload interface
- 🔍 **Automatic Analysis** - Runs all 100 CQL endgame scripts against your games
- ♟️ **Interactive Chess Boards** - View positions with chessboard.js
- 📊 **Grouped Results** - Results organized by endgame type (collapsible sections)
- 📝 **Complete Metadata** - Shows game info, players, event, date, move number
- 🎨 **Beautiful UI** - Modern, responsive design with gradient styling

## What It Does

The analyzer checks your PGN file against 100 classical endgame patterns including:
- King and pawn endgames
- Rook endgames
- Queen endgames
- Bishop endgames
- Knight endgames
- Complex piece combinations
- And many more!

For each matching pattern, it displays:
- The exact position as an interactive chess board
- Which players and game it came from
- The event and date
- The move number where the pattern occurred
- The complete FEN string

## Installation

### Prerequisites

1. Python 3.7 or higher
2. CQL binary (Chess Query Language)

### Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Update paths in `cql_analyzer_app.py`:
```python
# Line 20-21: Update these paths to match your system
CQL_BINARY = "/Users/elliottmacneil/python/chess-stuff/reti/bins/cql6-1/cql"
CQL_SCRIPTS_DIR = "/Users/elliottmacneil/python/chess-stuff/reti/cql-files/100endings"
```

## Running the App

1. Start the Flask server:
```bash
python cql_analyzer_app.py
```

2. Open your browser to:
```
http://127.0.0.1:5000
```

3. Upload a PGN file and click "Analyze PGN"

4. Wait for analysis to complete (may take 1-2 minutes for large files)

5. View results grouped by ending type - click on any ending type to expand and see positions

## Project Structure

```
.
├── cql_analyzer_app.py      # Main Flask application
├── requirements.txt          # Python dependencies
├── templates/
│   └── index.html           # Web interface HTML/CSS/JS
└── README_webapp.md         # This file
```

## How It Works

### Backend (Flask)
1. Accepts PGN file upload
2. Saves file temporarily
3. Runs all .cql scripts from the 100endings directory
4. For each script that finds matches:
   - Counts matching games
   - Extracts positions marked with {CQL}
   - Collects game metadata
5. Returns JSON with grouped results

### Frontend (HTML/JS)
1. Drag-and-drop file upload interface
2. Displays analysis progress
3. Groups results by ending type
4. Renders chess boards using chessboard.js
5. Collapsible sections for each ending type
6. Shows complete position metadata

## Configuration Options

### File Size Limit
Default: 16MB. To change, edit `cql_analyzer_app.py`:
```python
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # bytes
```

### CQL Timeout
Default: 30 seconds per script. To change, edit the `run_cql_script` function:
```python
result = subprocess.run(
    [...],
    timeout=30  # seconds
)
```

### Port
Default: 5000. To change, edit the bottom of `cql_analyzer_app.py`:
```python
app.run(debug=True, port=5000)
```

## Example Usage

### Analyzing Your Games

1. Export your games from Chess.com, Lichess, or any chess database as PGN
2. Upload to the web interface
3. View which classical endgames appeared in your games
4. Study the positions that match famous endgame patterns

### Finding Specific Patterns

The analyzer checks against patterns like:
- **1_5KP**: King and pawn endgames
- **52_68RPr**: Rook and pawn endgames
- **100Qrp**: Queen and pawn endgames
- **93BN**: Bishop and knight endgames
- And 96 more patterns!

## Troubleshooting

### "CQL binary not found"
- Check the CQL_BINARY path in the script
- Make sure CQL is installed and the path is correct
- Test CQL works: `/path/to/cql --version`

### "CQL scripts directory not found"
- Check the CQL_SCRIPTS_DIR path in the script
- Make sure all .cql files are in that directory

### "Analysis taking too long"
- Large PGN files (thousands of games) can take several minutes
- Check terminal output for progress
- Consider testing with a smaller PGN file first

### "No matching endgames found"
- Your PGN file might not contain positions matching any of the 100 patterns
- Try analyzing games that reach endgames (not short tactical games)
- Check that your PGN file is properly formatted

### Board not displaying
- Check browser console for JavaScript errors
- Make sure you have internet connection (chessboard.js loads from CDN)
- Try refreshing the page

## Advanced: Understanding CQL Scripts

Each .cql file defines a pattern using Chess Query Language. For example:

- `1_5KP.cql` - Finds king and pawn endgames
- `52_68RPr.cql` - Finds Lucena/Philidor rook endgame patterns
- `100Qrp.cql` - Finds queen vs rook endgames

When a position in your PGN matches a pattern, CQL marks it with a `{CQL}` comment.

## Technical Details

### Stack
- **Backend**: Flask (Python)
- **Chess Logic**: python-chess library
- **CQL Engine**: External CQL binary
- **Frontend**: Vanilla JavaScript
- **Chess Board**: chessboard.js
- **Styling**: Pure CSS with gradients

### Performance
- Each CQL script runs independently
- Scripts run sequentially (not parallel)
- Typical analysis time: 1-3 minutes for 1000-game PGN
- Positions are extracted only from matching games

## Future Enhancements

Possible improvements:
- [ ] Parallel CQL script execution for faster analysis
- [ ] Download results as PGN files
- [ ] Export positions as images or PDF
- [ ] Filter results by date, player, event
- [ ] Search within results
- [ ] Save analysis results for later viewing
- [ ] Compare multiple PGN files
- [ ] Show statistics (most common endings, etc.)

## License

This is a personal project for analyzing chess games. CQL and chess.js libraries have their own licenses.

## Credits

- Built on top of existing analyse_cql.py functionality
- Uses chessboard.js for board visualization
- CQL by Gady Costeff
- python-chess library by Niklas Fiekas
