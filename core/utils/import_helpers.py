# core/utils/import_helpers.py

import gspread
from google.oauth2.service_account import Credentials
from core.models import Category, Item

def import_category_from_sheet(sheet, google_sheets_credentials):
    """
    Imports items from a single gspread worksheet.
    Returns dict with summary info.
    """
    category_name = sheet.title.strip()
    category_obj, _ = Category.objects.get_or_create(name=category_name)

    all_data = sheet.get_all_values()
    if len(all_data) < 2:
        return {
            "category_name": category_name,
            "items_processed": 0,
            "message": f"Category '{category_name}' has no data to import."
        }

    header_row, item_rows = all_data[0], all_data[1:]

    try:
        sku_col_index = header_row.index('SKU')
        desc_col_index = header_row.index('Barcode Description')
        price_col_index = header_row.index('Price')
        inventory_col_index = header_row.index('Inventory')
    except ValueError as e:
        raise ValueError(f"Missing required column in category '{category_name}': {e}")

    skus_from_sheet = set()

    for row in item_rows:
        def get_cell_data(col_index):
            return row[col_index].strip() if len(row) > col_index else ""

        sku = get_cell_data(sku_col_index)
        if not sku:
            continue
        skus_from_sheet.add(sku)

        price_string = get_cell_data(price_col_index)
        price_to_save = "0" if not price_string else price_string

        inventory_value = get_cell_data(inventory_col_index)
        inventory_to_save = "0" if not inventory_value else inventory_value

        Item.objects.update_or_create(
            sku=sku,
            defaults={
                'name': get_cell_data(desc_col_index) or 'No Name Provided',
                'price': price_to_save,
                'inventory': inventory_to_save,
                'category': category_obj
            }
        )

    # Return summary
    return {
        "category_name": category_name,
        "items_processed": len(skus_from_sheet),
        "message": f"Imported {len(skus_from_sheet)} items from category '{category_name}'."
    }
