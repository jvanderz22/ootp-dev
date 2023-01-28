import re
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from draft_class_files import get_draft_class_drafted_players_file
from constants import DRAFT_CLASS_NAME, STATS_PLUS_URL


def go_to_round(driver, round):
    button = driver.find_element(By.CSS_SELECTOR, f'button[data-round-num="{round}"]')
    button.click()
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, f'button[data-round-num="{round}"].activetext')
        )
    )


def save_drafted_players(driver):
    data = []
    round = 1
    while round <= 20:
        print(f"Loading data for round {round}")
        go_to_round(driver, round)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        table = soup.find("table", {"class": "draftmaintable"})
        table_rows = table.find_all("tr")[1:]
        row_round = table_rows[1].find("td").get_text()
        if int(row_round) != round:
            print(f"Could not load round {round}. Exiting.")
            raise RuntimeError("Error loading data.")
        empty_row = False
        for table_row in table_rows:
            row_data = []
            for i, td in enumerate(table_row.find_all("td")):
                try:
                    text_data = td.get_text().strip()
                    if i == 4 and len(text_data) == 0:
                        empty_row = True
                    text_data = re.sub("\n.*\nA", "", text_data)
                    row_data.append(text_data)
                except:
                    continue
            if empty_row:
                break
            if len(row_data) > 0:
                data.append(row_data)
        if empty_row:
            break
        round += 1
    draft_class_file = get_draft_class_drafted_players_file()
    headers = ["Round", "Pick", "Overall", "Team", "Selection", "Time"]
    data_frame = pd.DataFrame(data=data, columns=headers)
    data_frame.to_csv(draft_class_file, index=False)


def build_drafted_players_list():
    drafted_players_url = f"{STATS_PLUS_URL}/draft/#current"
    print(
        f"Building drafted players list for {DRAFT_CLASS_NAME} from {drafted_players_url}"
    )
    driver = webdriver.Chrome()
    driver.get(drafted_players_url)
    save_drafted_players(driver)


if __name__ == "__main__":
    build_drafted_players_list()
