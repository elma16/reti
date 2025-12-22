#!/usr/bin/env python3

import argparse
import requests
import csv
from bs4 import BeautifulSoup


def fetch_table_data(url):
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch the page. Status code: {response.status_code}")
        return None
    return response.text


def parse_table_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table")
    if not table:
        print("No table found in the HTML.")
        return None

    headers = []
    data_rows = []

    # Extract headers
    for th in table.find_all("th"):
        headers.append(th.text.strip())

    # Extract data rows
    for tr in table.find_all("tr"):
        row_data = [td.text.strip() for td in tr.find_all("td")]
        if row_data:
            data_rows.append(row_data)

    return headers, data_rows


def write_to_csv(headers, data_rows, output_file):
    with open(output_file, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(headers)
        writer.writerows(data_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch and convert HTML table from a URL to a CSV file."
    )
    parser.add_argument("url", help="URL containing the table to be converted.")
    parser.add_argument(
        "-o",
        "--output",
        default="table_data.csv",
        help="Output CSV file name. Default is 'table_data.csv'.",
    )
    args = parser.parse_args()

    url = args.url
    url = "https://www.ecfrating.org.uk/v2/new/list_games_player.php?domain=S&year=ALL&show_games=on&show_ratings=on&ECF_code=315385L"
    output_csv_file = args.output

    html_content = fetch_table_data(url)
    if html_content:
        headers, data_rows = parse_table_html(html_content)
        if headers and data_rows:
            write_to_csv(headers, data_rows, output_csv_file)
            print(f"Data successfully extracted and saved to '{output_csv_file}'.")
        else:
            print("Failed to parse table data.")
    else:
        print("Failed to fetch the page.")
