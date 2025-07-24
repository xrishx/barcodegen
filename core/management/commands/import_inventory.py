import gspread
from django.core.management.base import BaseCommand
from django.conf import settings 
from google.oauth2.service_account import Credentials
from core.models import Category, Item

class Command(BaseCommand):
    help = 'Synchronizes inventory from Google Sheet to the database (Adds, Updates, and Deletes).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting inventory synchronization...'))

        try:
            # --- NEW: Step 1 - Initialize a set to hold all SKUs from the sheet ---
            skus_from_sheet = set()

            # 1. AUTHENTICATE
            scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            creds = Credentials.from_service_account_info(settings.GOOGLE_SHEETS_CREDENTIALS, scopes=scopes)
            client = gspread.authorize(creds)
            spreadsheet = client.open('MASTER LIST 2 - v2.updated one')
            self.stdout.write(self.style.SUCCESS(f"Successfully opened spreadsheet: 'MASTER LIST 2 - v2.updated one'"))

            # 2. GET SHEETS
            all_worksheets = spreadsheet.worksheets()
            category_sheets = all_worksheets[4:]

            # 3. PROCESS EACH CATEGORY SHEET (ADD & UPDATE)
            for sheet in category_sheets:
                category_name = sheet.title.strip()
                self.stdout.write(f"\nProcessing sheet for category: '{category_name}'")
                category_obj, _ = Category.objects.get_or_create(name=category_name)
                all_data = sheet.get_all_values()
                if len(all_data) < 2: 
                    continue
                header_row, item_rows = all_data[0], all_data[1:]

                try:
                    sku_col_index = header_row.index('SKU')
                    desc_col_index = header_row.index('Barcode Description')
                    price_col_index = header_row.index('Price')
                    inventory_col_index = header_row.index('Inventory')  # Added Inventory column index
                except ValueError as e:
                    self.stderr.write(self.style.ERROR(f"  -> CRITICAL: Sheet '{category_name}' missing column: {e}. Skipping sheet."))
                    continue

                for row_num, row in enumerate(item_rows, start=2):
                    def get_cell_data(col_index):
                        return row[col_index].strip() if len(row) > col_index else ""

                    sku = get_cell_data(sku_col_index)
                    if not sku: 
                        continue

                    # Add SKU to master set
                    skus_from_sheet.add(sku)

                    price_string = get_cell_data(price_col_index)
                    price_to_save = "0" if not price_string else price_string

                    inventory_value = get_cell_data(inventory_col_index)
                    inventory_to_save = "0" if not inventory_value else inventory_value  # Default to 0 if empty

                    Item.objects.update_or_create(
                        sku=sku,
                        defaults={
                            'name': get_cell_data(desc_col_index) or 'No Name Provided',
                            'price': price_to_save,
                            'inventory': inventory_to_save,  # Save inventory value
                            'category': category_obj
                        }
                    )
            
            self.stdout.write(self.style.SUCCESS('\nFinished processing sheet data. All items created or updated.'))

            # --- Handle Deletions ---
            self.stdout.write("\nChecking for items to delete...")

            # Get all SKUs currently in our database
            skus_in_db = set(Item.objects.values_list('sku', flat=True))

            # Find SKUs in DB but NOT in sheet
            skus_to_delete = skus_in_db - skus_from_sheet

            if skus_to_delete:
                self.stdout.write(self.style.WARNING(f"Found {len(skus_to_delete)} items to delete."))
                deleted_count, _ = Item.objects.filter(sku__in=skus_to_delete).delete()
                self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} items."))
            else:
                self.stdout.write(self.style.SUCCESS("No items to delete. Database is up to date."))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred: {e}"))
            import traceback
            traceback.print_exc()
        
        self.stdout.write(self.style.SUCCESS('\nInventory synchronization finished.'))
        self.stdout.write(self.style.SUCCESS('All operations completed successfully.'))
        