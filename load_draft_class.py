import getopt
import sys
import pandas as pd
from bs4 import BeautifulSoup


def create_csv(file_path, draft_class_path):
    header = []
    data = []
    soup = BeautifulSoup(open(file_path), "html.parser")
    table = soup.find_all("table")[0].find_all("tr")[1].find("table")
    header_row = table.find("tr")

    for th in header_row.find_all("th"):
        try:
            header.append(th.get_text())
        except:
            continue

    table_rows = table.find_all("tr")[2:]

    for table_row in table_rows:
        row_data = []
        for td in table_row.find_all("td"):
            try:
                row_data.append(td.get_text())
            except:
                continue
        data.append(row_data)

    data_frame = pd.DataFrame(data=data, columns=header)
    data_frame.to_csv(draft_class_path)


if __name__ == "__main__":
    class_name = None
    file_name = None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "f:c:")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-f":
            file_name = arg
        if opt == "-c":
            class_name = arg
    if class_name is None:
        print("Class name (-c) not specified.")
        sys.exit(2)
    if file_name is None:
        print("File name (-f) not specified.")

    file_name = file_name.replace("%20", " ")
    class_path = f"datasets/{class_name}.csv"
    create_csv(file_name, class_path)
    print(
        f'Created class at {class_path}. Set "{class_name}" to be the active draft class in constants.py to process it.'
    )
