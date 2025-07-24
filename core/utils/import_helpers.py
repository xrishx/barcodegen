# core/utils/import_helpers.py

import gspread
from django.db import transaction
from core.models import Category, Item

@transaction.atomic # This is crucial! Wraps the entire operation in a database transaction.
def import_category_from_sheet(sheet: gspread.Worksheet, google_sheets_credentials=None):
    """
    Synchronizes all items for a given category from a single gspread worksheet.
    - Creates new items.
    - Updates existing items.
    - Deletes items from the database that are no longer in the sheet.
    
    Returns a dictionary summarizing the operation.
    The 'google_sheets_credentials' argument is kept for compatibility but is not used.
    """
    category_name = sheet.title.strip()
    category_obj, _ = Category.objects.get_or_create(name=category_name)

    # --- Step 1: Fetch data from the sheet and prepare for sync ---
    all_data = sheet.get_all_values()
    
    # If the sheet is empty (only header or less), delete all DB items for this category
    if len(all_data) < 2:
        deleted_count, _ = Item.objects.filter(category=category_obj).delete()
        return {
            "category_name": category_name,
            "items_processed": 0,
            "created": 0,
            "updated": 0,
            "deleted": deleted_count,
            "message": f"Sync complete for '{category_name}'. Sheet was empty, {deleted_count} items removed."
        }

    header_row, item_rows = all_data[0], all_data[1:]

    # Use your original method for finding column indices
    try:
        sku_col_index = header_row.index('SKU')
        desc_col_index = header_row.index('Barcode Description')
        price_col_index = header_row.index('Price')
        inventory_col_index = header_row.index('Inventory')
    except ValueError as e:
        raise ValueError(f"Missing required column in category '{category_name}': {e}")

    # This set will hold all SKUs found in the Google Sheet. It's vital for the deletion step.
    skus_from_sheet = set()
    created_count = 0
    updated_count = 0

    # --- Step 2: Loop through sheet rows to CREATE and UPDATE items ---
    for row in item_rows:
        def get_cell_data(col_index):
            return row[col_index].strip() if len(row) > col_index else ""

        sku = get_cell_data(sku_col_index)
        if not sku:
            continue  # Skip rows without a SKU
        
        # Add the valid SKU to our set for later comparison
        skus_from_sheet.add(sku)

        # Your original logic for handling price and inventory data
        price_string = get_cell_data(price_col_index)
        price_to_save = "0" if not price_string else price_string

        inventory_value = get_cell_data(inventory_col_index)
        inventory_to_save = "0" if not inventory_value else inventory_value

        # Use update_or_create and check the 'created' flag
        item, created = Item.objects.update_or_create(
            sku=sku,
            defaults={
                'name': get_cell_data(desc_col_index) or 'No Name Provided',
                'price': price_to_save,
                'inventory': inventory_to_save,
                'category': category_obj
            }
        )

        if created:
            created_count += 1
        else:
            updated_count += 1

    # --- Step 3: Identify and DELETE items that are in the DB but not the sheet ---
    
    # Get a set of all SKUs currently in the database for this category
    db_skus = set(Item.objects.filter(category=category_obj).values_list('sku', flat=True))

    # Find the difference: SKUs that are in the database but were NOT in the sheet we just processed
    skus_to_delete = db_skus - skus_from_sheet

    deleted_count = 0
    if skus_to_delete:
        # Perform a single, efficient bulk delete operation
        items_deleted_query = Item.objects.filter(category=category_obj, sku__in=skus_to_delete)
        deleted_count = items_deleted_query.count()
        items_deleted_query.delete()


    # --- Step 4: Return a detailed summary ---
    summary_message = (
        f"Sync for '{category_name}' complete. "
        f"Created: {created_count}, Updated: {updated_count}, Removed: {deleted_count}."
    )

    return {
        "category_name": category_name,
        "items_processed": len(skus_from_sheet),
        "created": created_count,
        "updated": updated_count,
        "deleted": deleted_count,
        "message": summary_message,
    }