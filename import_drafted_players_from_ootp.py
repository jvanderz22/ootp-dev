import getopt
import sys
import pandas as pd
from bs4 import BeautifulSoup
import csv

from draft_class_files import get_draft_class_drafted_players_file
from constants import DRAFT_CLASS_NAME


def save_drafted_players(file):
    header = []
    data = []
    soup = BeautifulSoup(open(file), "html.parser")
    table = soup.find_all("table")[0].find_all("tr")[1].find("table")
    header_row = table.find("tr")

    for th in header_row.find_all("th"):
        try:
            header.append(th.get_text())
        except:
            continue

    table_rows = table.find_all("tr")[1:]

    for table_row in table_rows:
        row_data = []
        for td in table_row.find_all("td"):
            try:
                row_data.append(td.get_text())
            except:
                continue
        rows = [row.strip() for row in row_data]
        data.append(rows)

    data_frame = pd.DataFrame(data=data, columns=header)
    players = data_frame.to_dict("records")
    draft_class_file = get_draft_class_drafted_players_file()
    headers = ["Round", "Pick", "Overall", "Team", "Selection", "Time"]
    with open(draft_class_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        for player in players:
            writer.writerow(
                {
                    "Round": player["Round"],
                    "Overall": player["OA Pick"],
                    "Pick": player["Pick"],
                    "Team": player["DrTm"],
                    "Selection": f"{player['POS']} {player['Name']}",
                    "Time": "",
                }
            )


if __name__ == "__main__":
    file_name = None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "f:")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-f":
            file_name = arg
    if file_name is None:
        print("File name (-f) not specified.")
        sys.exit(2)

    file_name = file_name.replace("%20", " ")
    file_name = file_name.replace("file://", "")
    save_drafted_players(file_name)
