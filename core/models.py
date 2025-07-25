from django.db import models

class DashboardStats(models.Model):
    """
    A simple model to store pre-calculated statistics for fast dashboard loading.
    This table should only ever have a single row.
    """
    total_items = models.IntegerField(default=0)
    total_categories = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Stats as of {self.last_updated}"

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Categories"

class Item(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    price = models.CharField(max_length=50, blank = True, null=True)
    sku = models.CharField(max_length=13, unique=True, db_index=True)
    inventory = models.CharField(max_length=13, default="0")  # Default inventory to "0"
    category = models.ForeignKey(Category, related_name='items', on_delete=models.CASCADE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
