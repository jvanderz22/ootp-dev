import getopt
import os
import sys
import json
import pyautogui
import time
import ScriptingBridge
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps
from load_draft_class import create_csv


ootp_app = [
    x
    for x in NSWorkspace.sharedWorkspace().runningApplications()
    if x.bundleIdentifier() == "com.ootpdevelopments.ootp26macsteam"
][0]

chrome = ScriptingBridge.SBApplication.applicationWithBundleIdentifier_(
    "com.google.Chrome"
)


def click(x, y):
    time.sleep(0.1)
    pyautogui.moveTo(x, y)
    time.sleep(0.01)
    pyautogui.mouseDown()
    time.sleep(0.05)
    pyautogui.mouseUp()


class PlayerListOOTPPage:
    def __init__(self, page_has_option_bar):
        size = pyautogui.size()
        player_list_offset = 80 if page_has_option_bar is True else 0

        self.button_row_vert_loc = 290 + player_list_offset
        self.next_button_horz_loc = size.width - 75
        self.first_page_button_horz_loc = size.width - 235
        self.reports_button_horz_location = 800

    def get_downloaded_report_path(self):
        click(self.reports_button_horz_location, self.button_row_vert_loc)
        time.sleep(0.01)
        click(self.reports_button_horz_location, self.button_row_vert_loc + 30)
        time.sleep(0.01)
        report_path = get_file_path()
        return report_path

    def go_to_first_page(self):
        click(self.first_page_button_horz_loc, self.button_row_vert_loc)

    def go_to_next_page(self):
        click(self.next_button_horz_loc, self.button_row_vert_loc)


def activate_ootp():
    ootp_app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    time.sleep(0.02)
    pyautogui.click(50, 50)


def get_file_path():
    if not chrome.windows():
        return "No active window"

    window = chrome.windows()[0]  # Get the first window
    tab = window.activeTab()  # Get the active tab in the window
    tab_url = tab.URL()  # Get the URL of the active tab
    url = tab_url.replace("file://", "").replace("%20", " ")
    tab.close()
    return url


def load_data_into_file(file_path, num_pages, page_has_option_bar):
    ootp_page = PlayerListOOTPPage(page_has_option_bar)
    activate_ootp()
    time.sleep(1)
    ootp_page.go_to_first_page()
    time.sleep(1)

    cur_page = 1
    download_path = ootp_page.get_downloaded_report_path()
    time.sleep(0.2)
    create_csv(download_path, file_path)
    activate_ootp()
    time.sleep(0.2)

    while cur_page < num_pages:
        ootp_page.go_to_next_page()
        time.sleep(0.01)
        download_path = ootp_page.get_downloaded_report_path()
        create_csv(download_path, "temp.csv")
        with open("temp.csv", "r") as file:
            data = file.readlines()
            with open(file_path, "a") as final_file:
                # Don't write the header line multiple times
                final_file.writelines(data[1:])
        activate_ootp()
        cur_page += 1
    ootp_app.hide()


def create_dataset(dataset_name, num_pages, page_has_option_bar):
    dataset_path = f"datasets/{dataset_name}.csv"
    data_directory = f"processed_classes/{dataset_name}"
    load_data_into_file(dataset_path, num_pages, page_has_option_bar)
    if not os.path.exists(data_directory):
        os.makedirs(data_directory)
    dataset_config = {
        "ranking_method": "draft_class",
    }
    config_file_path = f"{data_directory}/config.json"
    if not os.path.exists(config_file_path):
        with open(config_file_path, "w") as config_file:
            config_file.write(json.dumps(dataset_config, indent=4))
        print(
            f'Created class at {dataset_path}. Set "{dataset_name}" to be the active dataset in constants.py to process it.'
        )
    else:
        print(
            f'Updated class at {dataset_path}. Set "{dataset_name}" to be the active dataset in constants.py to process it.'
        )
    print(f"Settings can be updated in processed_classes/{dataset_name}/config.json.")


if __name__ == "__main__":
    dataset_name = None
    dataset_pages = None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "p:d:")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-d":
            dataset_name = arg
        if opt == "-p":
            dataset_pages = int(arg)
    if dataset_name is None:
        print("Dataset name (-d) not specified.")
        sys.exit(2)
    if dataset_pages is None:
        print("Dataset pages (-p) not specified.")
        sys.exit(2)

    print(
        """
Confirm OOTP is open to the players list page you want to import, with the correct view selected and sorted in the desired manner.

On that page, is there an option bar to "Include Retired Players", etc - y/n?"""
    )
    page_has_option_bar = None
    while page_has_option_bar is None:
        user_input = input()
        if user_input.lower() == "y":
            page_has_option_bar = True
        elif user_input.lower() == "n":
            page_has_option_bar = False
        else:
            print(
                """Is there an option bar on the page to "Include Retired Players", etc - y/n?"""
            )
    create_dataset(dataset_name, dataset_pages, page_has_option_bar)
