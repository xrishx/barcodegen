# core/filters.py

from django_filters import rest_framework as filters
from .models import Item

class ItemFilter(filters.FilterSet):
    # This explicitly defines a filter named 'category' for the Item model.
    # It will filter based on the 'id' of the related Category object.
    # The lookup_expr='exact' is the default, but we're being clear.
    category = filters.NumberFilter(field_name='category__id', lookup_expr='exact')

    class Meta:
        model = Item
        # These are the fields our FilterSet will manage.
        fields = ['category']