from rest_framework import serializers
from .models import Category, Item

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']

class ItemSerializer(serializers.ModelSerializer):
    # This will display the category name instead of just its ID number.
    category = serializers.StringRelatedField()

    class Meta:
        model = Item
        # These are the fields that will be included in the API response
        fields = ['name', 'price', 'sku', 'category']
        