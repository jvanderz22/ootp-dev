Commands:

Get data from exported game file:

python3 load_draft_class.py -c draft-class-name -f /path/to/file.csv

Run evals on draft class:
python3 run.py

Print top available players:
python3 print_evals.py

Populate drafted players from statsplus:
python3 import_drafted_players.py

Create a new file of rankings:
python3 rankings_csv.py

Optionally add a custom modifier to change value of position:
python3 rankings_csv.py --C 0.9

Upload draft preference list to stats plus:
python3 upload_drafted_players.py
