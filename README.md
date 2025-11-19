Activate the virtual env: `source activate/bin/activate`

Commands:

Get data from exported game file:

python3 load_draft_class.py -c draft-class-name -f /path/to/file.html

Run evals on draft class:
python3 run.py

Print top available players:
python3 print_evals.py

Print org summaries:
python3 print_org_summaries.py

Populate drafted players from statsplus:
python3 import_drafted_players.py

Create a new file of rankings:
python3 rankings_csv.py

Optionally add a custom modifier to change value of position:
python3 rankings_csv.py --C 0.9

Upload draft preference list to stats plus:
python3 upload_drafted_players.py

Refresh drafted list and upload draft preference list to stats plus:
python3 upload_drafted_players.py -d

Possible ranking_method: "draft_class", "potential" and "overall"
Possible print_method: "draft_prospects" and "org_players"

Build a list from in-game instead of from an exported report. Requires having
game open to player page list. Takes option -p for the number of pages of players
on the in-game report
python3 import_dataset_from_ootp.py -d dataset_name -p 120
