from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Categories"

class Item(models.Model):
    name = models.CharField(max_length=200)
    price = models.CharField(max_length=50, blank = True, null=True)
    sku = models.CharField(max_length=13, unique=True)
    inventory = models.CharField(max_length=13, default="0")  # Default inventory to "0"
    category = models.ForeignKey(Category, related_name='items', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
