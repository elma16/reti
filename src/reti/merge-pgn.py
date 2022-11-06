import glob

read_files = glob.glob("*.pgn")

with open("result.pgn", "wb") as outfile:
    for f in read_files:
        with open(f, "rb") as infile:
            outfile.write(infile.read())