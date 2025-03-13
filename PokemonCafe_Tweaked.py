import os
import re
import sys
import argparse
import subprocess
from time import sleep
from typing import List, Optional
from datetime import date, datetime, time, timedelta, timezone

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException, InvalidSessionIdException, NoSuchWindowException


def wait_until_datetime(target: datetime) -> None:
    while True:
        now = datetime.now(target.tzinfo)
        if now >= target:
            print("Target time reached!")
            break
        else:
            time_to_wait = (target - now).total_seconds()
            sleep(time_to_wait)


def wait_until_not_found(driver: webdriver.Chrome, text_to_find: str, check_interval: float | int) -> None:
    while True:
        try:
            # Check if the text is present in the page source
            if driver.page_source == None or text_to_find in driver.page_source:
                sleep(check_interval)  # Wait before checking again
            else:
                break
        except NoSuchElementException:
            break

def safe_find_element(driver: webdriver.Chrome | WebElement, by: By, value: Optional[str]) -> WebElement | None:
    try:
        return driver.find_element(by, value)
    except NoSuchElementException:
        return None


def safe_find_elements(driver: webdriver.Chrome | WebElement, by: By, value: Optional[str]) -> List[WebElement]:
    try:
        return driver.find_elements(by, value)
    except NoSuchElementException:
        return []


def select_best_time(time_slots: List[time], min_time: Optional[time], max_time: Optional[time]) -> time | None:
    if not time_slots:
        return None
    if not min_time and not max_time:
        return time_slots[0]
    if min_time and max_time:
        for time_slot in time_slots:
            if time_slot >= min_time and time_slot <= max_time:
                return time_slot
        return None
    elif min_time:
        latest_time = None
        for time_slot in time_slots:
            if time_slot >= min_time:
                if not latest_time or time_slot > latest_time:
                    latest_time = time_slot
        return latest_time
    elif max_time:
        earliest_time = None
        for time_slot in time_slots:
            if time_slot <= max_time:
                if not earliest_time or time_slot < earliest_time:
                    earliest_time = time_slot
        return earliest_time
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Semi-automatically book a Pokemon Cafe visit."
    )
    parser.add_argument("-c", "--city", dest="city",
                        choices=["tokyo", "osaka", "Tokyo", "Osaka"],
                        help="Whether you want to book in Tokyo or Osaka.",
                        required=True)
    parser.add_argument("-g", "--guests", dest="guests",
                        choices=["1", "2", "3", "4", "5", "6"],
                        help="Number of guests ranging from 1 to 6.",
                        required=True)
    parser.add_argument("-d", "--date", dest="date", type=date.fromisoformat,
                        help="[yyyy-mm-dd] The date you want to book on. Uses Pokemon Cafe's date.",
                        required=True)
    parser.add_argument("-s", "--start", dest="minTime", type=time.fromisoformat,
                        help="[hh:mm] Earliest booking time, meaning it won't choose an earlier time on the given date. Uses Pokemon Cafe's time.",
                        required=False)
    parser.add_argument("-e", "--end", dest="maxTime", type=time.fromisoformat,
                        help="[hh:mm] Latest booking time, meaning it won't choose an earlier time on the given date. Uses Pokemon Cafe's time.",
                        required=False)
    parser.add_argument("-w", "--wait", dest="wait", action="store_true",
                        help="Including this flag will postpone running the script until a minute before reservations for your selected date become available (which happens 31 days prior at 6pm Pokemon Cafe time)",
                        required=False)

    args = parser.parse_args()
    print(f"Running script with the following arguments: {args}")

    # The websites are identical, so we can use the same code for both. The only difference is the URL.
    website = ""
    if args.city.lower() == "tokyo":
        website = "https://reserve.pokemon-cafe.jp/reserve/step1"
    elif args.city.lower() == "osaka":
        website = "https://osaka.pokemon-cafe.jp/reserve/step1"
    else:
        parser.error(
            "Invalid city argument. Please choose either Tokyo and Osaka.")

    # Validate the time arguments
    if args.minTime and args.maxTime and args.minTime >= args.maxTime:
        parser.error(
            "The earliest booking time must be before the latest booking time.")

    # Tell user about expected behavior
    if args.minTime and args.maxTime:
        print(
            f"The script will only attempt to book a time between {args.minTime} and {args.maxTime} on the selected date.")
    elif args.minTime:
        print(
            f"The script will only attempt to book a time after {args.minTime} on the selected date. It will prefer later times if multiple are available.")
    elif args.maxTime:
        print(
            f"The script will only attempt to book a time before {args.maxTime} on the selected date. It will prefer earlier times if multiple are available.")

    # Throws an error if the number of guests is not an integer
    guests = int(args.guests)

    # Validate the date argument
    today = date.today()
    if args.date < today:
        parser.error("The date you want to book on is in the past.")

    # Handle waiting behavior
    japan_tz = timezone(timedelta(hours=9))
    reservations_open = datetime(args.date.year, args.date.month,
                                args.date.day, 18, 0, 0, tzinfo=japan_tz) - timedelta(days=31)
    now = datetime.now(japan_tz)
    if args.wait:
        print(
            f"Reservations for the {args.date} are expected to open at {reservations_open.astimezone()}")
        target_time = reservations_open - timedelta(minutes=1)
        if now < target_time:
            print(
                f"Waiting until a minute before reservations open... ({target_time.astimezone()})")
            wait_until_datetime(reservations_open)
        else:
            print("Reservations for the selected date have already opened, skipping wait. Note that it's possible that reservations are already full.")

    # Start the WebDriver
    chrome_options = Options()
    chrome_options.add_experimental_option("detach", True)
    service = Service(
        popen_kw={"creation_flags": subprocess.CREATE_NEW_PROCESS_GROUP})
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get(website)

    interval = 2

    try:
        while True:
            # Wait until the page is fully loaded by checking that the title is not empty
            if (not driver.title or not driver.page_source):
                sleep(interval)
                continue

            # Wait for captcha
            if ("confirm you are human" in driver.page_source):
                print("Captcha detected. Please solve it manually.")
                sleep(interval)
                continue

            # Check for terms and conditions
            if ("/ Agree to terms" in driver.page_source):
                agree_checkbox = safe_find_element(driver,
                                                By.CSS_SELECTOR,
                                                "#agreeChecked:not(:checked)")
                if agree_checkbox:
                    print("Checking terms checkbox.")
                    agree_checkbox_label = safe_find_element(driver,
                                                            By.CSS_SELECTOR,
                                                            "label.agreeChecked")
                    if agree_checkbox_label:
                        agree_checkbox_label.click()
                        continue
                    else:
                        print("WARN: Terms checkbox label not found.")
                        sleep(interval)
                        continue

                agree_button = safe_find_element(driver,
                                                By.CSS_SELECTOR,
                                                "#forms-agree .button-container-agree button:not(:disabled)")
                if agree_button:
                    print("Clicking terms agree button.")
                    # Sometimes no available seats puts you on the terms page again, so refresh later after agreeing
                    if ("no available seats can be found" in driver.page_source):
                        print("No available seats found, refreshing...")
                        agree_button.click()
                        sleep(interval)
                        driver.refresh()
                    else:
                        agree_button.click()
                    continue

            if ("About Email Address Authentication" in driver.page_source):
                continue_button = safe_find_element(driver,
                                                    By.CSS_SELECTOR,
                                                    "a.button[href='/reserve/step1'] ")
                if continue_button:
                    print("Clicking continue button.")
                    continue_button.click()
                    continue

            # Reload the page if it's congested
            if ("congested" in driver.page_source):
                print("Site congested, refreshing...")
                sleep(interval)
                driver.refresh()
                continue

            # Table Reservation page
            if ("Table Reservation" in driver.page_source):
                time_table = safe_find_element(driver, By.ID, "time_table")
                if time_table:
                    time_slot_elements = safe_find_elements(
                        driver, By.CSS_SELECTOR, "#time_table .time-cell a")
                    if not time_slot_elements:
                        print("No time slots found, refreshing...")
                        sleep(interval)
                        driver.refresh()
                        continue

                    # We have at least one time slot
                    time_slot_texts = [
                        time_slot.text for time_slot in time_slot_elements]
                    # output: ['B席\n10:25~\n空席\nAvailable', 'C席\n10:40~\n空席\nAvailable']
                    print(f"Found available time slots: {time_slot_texts}")
                    time_slots = []
                    for time_slot_string in time_slot_texts:
                        extracted_time = re.search(
                            r"(\d{2}:\d{2})", time_slot_string)
                        if extracted_time[0]:
                            time_slots.append(datetime.strptime(
                                extracted_time[0], "%H:%M").time())
                    print(f"Extracted times: {time_slots}")

                    best_time_slot = select_best_time(
                        time_slots, args.minTime, args.maxTime)
                    if best_time_slot:
                        best_time_slot_index = time_slots.index(best_time_slot)
                        print(f"Selecting time slot {best_time_slot}...")
                        time_slot_elements[best_time_slot_index].click()
                        continue
                    else:
                        print("No available time slots within the specified time range.")
                        sleep(interval)
                        driver.refresh()
                        continue
                elif "complete your reservation" in driver.page_source:
                    print("Reservation waiting for completion.")
                    # TODO: Maybe autopopulate the fields and submit the form?
                    break
                else:
                    guests_selected = safe_find_element(driver,
                                                        By.CSS_SELECTOR,
                                                        f"option[selected='selected'][value='{guests}']")
                    if not guests_selected:
                        print("Selecting the number of guests.")
                        select = Select(driver.find_element(By.NAME, 'guest'))
                        select.select_by_index(guests)
                        continue

                    calendar_header = safe_find_element(driver,
                                                        By.CSS_SELECTOR,
                                                        "#step2-form h3")
                    if (calendar_header):
                        header_text = calendar_header.text
                        split_text = re.split('[^0-9]', header_text)
                        if len(split_text) >= 2:
                            selected_year = int(split_text[0])
                            selected_month = int(split_text[1])
                            if selected_year != args.date.year or selected_month != args.date.month:
                                if date(selected_year, selected_month, args.date.day) < args.date:
                                    next_month_button = safe_find_element(driver,
                                                                        By.CSS_SELECTOR,
                                                                        "div:nth-child(3) > .calendar-pager")
                                    if next_month_button:
                                        print("Selecting the next month.")
                                        next_month_button.click()
                                        continue
                                elif date(selected_year, selected_month, args.date.day) > args.date:
                                    previous_month_button = safe_find_element(driver,
                                                                            By.CSS_SELECTOR,
                                                                            "div:nth-child(1) > .calendar-pager")
                                    if previous_month_button:
                                        print("Selecting the previous month.")
                                        previous_month_button.click()
                                        continue
                        else:
                            print("WARN: Calendar header text not in expected format.")
                            sleep(interval)
                            continue

                        # Here we can assume we are in the correct month and year
                        date_cell = safe_find_element(
                            driver, By.XPATH, "//li[contains(@class, 'calendar-day-cell') and contains(., " + str(args.date.day) + ")]")
                        if date_cell:
                            if not "selected" in date_cell.get_dom_attribute("class"):
                                print("Selecting the day of the month.")
                                date_cell.click()
                                continue
                        else:
                            print("WARN: Correct month, but date cell not found.")
                            sleep(interval)
                            continue

                        # We have selected the correct date
                        next_button = safe_find_element(driver,
                                                        By.ID,
                                                        "submit_button")
                        if next_button:
                            print("Pressing Next step button.")
                            next_button.click()
                            continue
                        else:
                            print("WARN: Calendar next button not found.")

            sleep(interval)
            driver.refresh()
    except KeyboardInterrupt:
        input("Script stopped. Hit Enter to also close the browser. Ctrl+C again to fully stop the script without closing the browser.")
        driver.quit()
        service.stop()
        exit()
    except (InvalidSessionIdException, NoSuchWindowException):
        print("The browser session was closed. Exiting.")
        service.stop()
        exit()
