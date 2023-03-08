import getopt
import sys
import ranking_csv
import time
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from dotenv import load_dotenv
import os

from draft_class_files import get_draft_class_upload_players_file
from constants import STATS_PLUS_URL
from import_drafted_players import build_drafted_players_list


load_dotenv()


def login_to_stats_plus(driver):
    login = driver.find_element(By.CSS_SELECTOR, 'a[data-login="1"]')
    login.click()
    link = driver.find_element(
        By.CSS_SELECTOR,
        'div.container div.container a img[src$="statsplus_login_button.png"]',
    )
    link.click()
    user_name = os.environ.get("splus-user-name")
    password = os.environ.get("splus-password")
    user_name_field = driver.find_element(By.ID, "username")
    password_field = driver.find_element(By.ID, "password")
    user_name_field.send_keys(user_name)
    password_field.send_keys(password)
    driver.find_element(By.ID, "kc-login").click()


def upload_draft_list():
    driver = webdriver.Chrome()
    driver.get(STATS_PLUS_URL)
    login_to_stats_plus(driver)
    driver.get(f"{STATS_PLUS_URL}/draft/#mylist")
    wait = WebDriverWait(driver, 5)
    wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[type=file]#upload-button")
        )
    ).send_keys(os.path.abspath(get_draft_class_upload_players_file()))
    wait.until(
        EC.presence_of_element_located((By.XPATH, "//button[text()='Confirm']"))
    ).click()
    wait.until(
        EC.presence_of_element_located((By.XPATH, "//button[text()='ok']"))
    ).click()
    time.sleep(5)


if __name__ == "__main__":
    refresh_drafted_players = False
    rerank_players = True
    try:
        opts, args = getopt.getopt(sys.argv[1:], "di")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-d":
            refresh_drafted_players = True
        if opt == "-i":
            rerank_players = False

    if refresh_drafted_players:
        build_drafted_players_list()
        print("Retreived list of all drafted players.")
    else:
        print("Using existing list of all drafted players. (use -d to refresh.)")

    if rerank_players:
        ranking_csv.create_ranking_csv()
        print("Built new preference list. Use -i to ignore next time.")
    else:
        print("Using existing preference list")
    upload_draft_list()
    print("Uploaded new list to StatsPlus.")
