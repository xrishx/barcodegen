# core/management/commands/find_duplicates.py

import gspread
from django.core.management.base import BaseCommand
from django.conf import settings
from google.oauth2.service_account import Credentials

class Command(BaseCommand):
    help = 'Finds and reports duplicate SKUs within the Google Sheet.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Scanning for duplicate SKUs...'))
        
        # This dictionary will store {sku: sheet_name}
        seen_skus = {}
        duplicate_count = 0

        try:
            # (Standard Google Sheets authentication code...)
            scopes = [ 'https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive' ]
            creds = Credentials.from_service_account_file(settings.GOOGLE_SHEETS_CREDENTIALS_FILE, scopes=scopes)
            client = gspread.authorize(creds)
            spreadsheet = client.open(settings.GOOGLE_SHEETS_SPREADSHEET_NAME)
            
            all_worksheets = spreadsheet.worksheets()
            category_sheets = all_worksheets[4:]

            for sheet in category_sheets:
                sheet_name = sheet.title.strip()
                self.stdout.write(f"-> Scanning sheet: {sheet_name}")

                all_data = sheet.get_all_values()
                if len(all_data) < 2: continue
                header_row, item_rows = all_data[0], all_data[1:]

                try:
                    sku_col_index = header_row.index('SKU')
                except ValueError:
                    self.stderr.write(self.style.ERROR(f"  - Sheet '{sheet_name}' has no 'SKU' column. Skipping."))
                    continue
                
                for row_num, row in enumerate(item_rows, start=2):
                    sku = row[sku_col_index].strip() if len(row) > sku_col_index else ""
                    if not sku: continue

                    if sku in seen_skus:
                        duplicate_count += 1
                        self.stdout.write(self.style.WARNING(
                            f"  - DUPLICATE FOUND: SKU '{sku}' on row {row_num} of sheet '{sheet_name}' "
                            f"was already seen in sheet '{seen_skus[sku]}'."
                        ))
                    else:
                        seen_skus[sku] = sheet_name

            self.stdout.write(self.style.SUCCESS(f"\nScan complete. Found {duplicate_count} duplicate SKU entries."))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred: {e}"))