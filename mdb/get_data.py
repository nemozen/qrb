import argparse
import gspread
import os
import pandas as pd
import tempfile


# Mapping of CSV header to DB column names
COLUMN_MAP = {
    'Worker 1': 'worker',
    'IP': 'ip_address',
    'MAC Address': 'mac_address',
    'MAC Addr': 'mac_address',
    'MAC': 'mac_address',
    'Miner Type': 'type',
    'Type': 'type',
    'Location': 'location',
    'SN': 'serial_number',
    'Miner SN': 'serial_number',
    'Serial Number': 'serial_number',
    'Power SN': 'psu_serial_number'
}


def sync_sheets(json_key, spreadsheet_url, tab_names, cache=False):
    gc = gspread.service_account(filename=json_key)
    sh = None
    temp_dir = tempfile.gettempdir()

    for name in tab_names:
        output_file = os.path.join(temp_dir, f'{name}.csv')
        if cache and os.path.exists(output_file):
            #  Local file  already exists. Skipping Google Sheets download
            yield output_file 
            continue # Move to the next worksheet
        
        if not sh:
            print(f"Opening {spreadsheet_url} ...")
            sh = gc.open_by_url(spreadsheet_url)
        print(f"Downloading {name} ...")
        worksheet = sh.worksheet(name)
        records = worksheet.get_all_records()
        df = pd.DataFrame(records)
        df = df.dropna(how='all')
        # Standardize columns
        # We use errors='ignore' so it only renames what it finds
        df = df.rename(columns=COLUMN_MAP, errors='ignore')
        # Keep only the columns we actually want in our web app
        standard_columns = list(set(COLUMN_MAP.values()))
        valid_cols = [c for c in standard_columns if c in df.columns]
        df = df[valid_cols]

        df.to_csv(output_file)
        yield output_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--key_file', type=str, default="qrb-labs-mdb.json")
    parser.add_argument('--sheet_url', type=str, help="Google spreadsheet url")
    parser.add_argument('--worksheets', nargs='+',
                        help='list of worksheet names eg --worksheets "Miners" "Other miners"',  default=["Miners"])
    args = parser.parse_args()

    filenames = sync_sheets(args.key_file, args.sheet_url, args.worksheets)
    print(list(filenames))
