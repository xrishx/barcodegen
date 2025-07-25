# In core/utils/import_helpers.py

import gspread
from django.db import transaction
from core.models import Category, Item, DashboardStats
import logging

logger = logging.getLogger(__name__)

def update_dashboard_stats():
    """
    Recalculates and saves the total item and category counts.
    This is called after a sync operation.
    """
    total_items_count = Item.objects.count()
    total_categories_count = Category.objects.count()
    
    # Use update_or_create to ensure there's only ever one row in the table.
    stats, created = DashboardStats.objects.update_or_create(
        id=1, # Always update the row with ID=1
        defaults={
            'total_items': total_items_count,
            'total_categories': total_categories_count
        }
    )
    logger.info("Dashboard stats have been updated.")


@transaction.atomic
def import_category_from_sheet(sheet: gspread.Worksheet, google_sheets_credentials=None):
    """
    Optimized version of the sync function that uses bulk database operations.
    """
    category_name = sheet.title.strip()
    category_obj, _ = Category.objects.get_or_create(name=category_name)
    logger.info(f"Starting bulk import for category: {category_name}")

    # --- Step 1: Fetch data using your robust method ---
    all_data = sheet.get_all_values()
    if len(all_data) < 2:
        # This part of your original logic is already efficient.
        deleted_count, _ = Item.objects.filter(category=category_obj).delete()
        return {"message": f"Sync complete. Sheet '{category_name}' was empty, {deleted_count} items removed."}

    header_row, item_rows = all_data[0], all_data[1:]
    try:
        sku_col_index = header_row.index('SKU')
        desc_col_index = header_row.index('Barcode Description')
        price_col_index = header_row.index('Price')
        inventory_col_index = header_row.index('Inventory')
    except ValueError as e:
        raise ValueError(f"Missing required column in '{category_name}': {e}")

    # --- Step 2: Prepare all data in memory FIRST (No DB calls in this loop) ---
    sheet_data = {}
    skus_from_sheet = set()
    for row in item_rows:
        def get_cell_data(col_index):
            return row[col_index].strip() if len(row) > col_index else ""

        sku = get_cell_data(sku_col_index)
        if not sku:
            continue
        
        skus_from_sheet.add(sku)
        
        # Store all row data in a dictionary keyed by SKU
        sheet_data[sku] = {
            'name': get_cell_data(desc_col_index) or 'No Name Provided',
            'price': get_cell_data(price_col_index) or "0",
            'inventory': get_cell_data(inventory_col_index) or "0",
            'category': category_obj
        }

    # --- Step 3: Perform Bulk Database Operations ---
    
    # Fetch all relevant existing items from the DB in ONE query
    existing_items_map = {
        item.sku: item for item in Item.objects.filter(sku__in=skus_from_sheet)
    }

    items_to_create = []
    items_to_update = []

    for sku, data in sheet_data.items():
        if sku in existing_items_map:
            # Item exists, prepare for bulk update
            item = existing_items_map[sku]
            item.name = data['name']
            item.price = data['price']
            item.inventory = data['inventory']
            items_to_update.append(item)
        else:
            # Item is new, prepare for bulk create
            items_to_create.append(Item(sku=sku, **data))
    
    # Create all new items in ONE query
    if items_to_create:
        Item.objects.bulk_create(items_to_create, batch_size=500)

    # Update all existing items in ONE query
    if items_to_update:
        Item.objects.bulk_update(items_to_update, ['name', 'price', 'inventory'], batch_size=500)

    # --- Step 4: Deletion logic (your original logic is already efficient!) ---
    db_skus = set(Item.objects.filter(category=category_obj).values_list('sku', flat=True))
    skus_to_delete = db_skus - skus_from_sheet
    deleted_count = 0
    if skus_to_delete:
        deleted_count, _ = Item.objects.filter(category=category_obj, sku__in=skus_to_delete).delete()

    # --- Step 5: Return summary ---
    created_count = len(items_to_create)
    updated_count = len(items_to_update)
    summary_message = (
        f"Sync for '{category_name}' complete. "
        f"Created: {created_count}, Updated: {updated_count}, Removed: {deleted_count}."
    )
    logger.info(summary_message)
    return {
        "message": summary_message,
        "created": created_count,
        "updated": updated_count,
        "deleted": deleted_count
    }