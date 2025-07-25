from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ItemViewSet,
    login_view, dashboard_view,
    barcode_generator_view, generate_barcode_view, generate_label_view,
    import_category_view, category_sheet_names_view,
    existing_categories_view, import_chunked_view, import_category_by_name_view, dashboard_stats_view
)

router = DefaultRouter()
router.register(r'inventory/categories', CategoryViewSet, basename='category')
router.register(r'inventory/items', ItemViewSet, basename='item')

urlpatterns = [
    path('', include(router.urls)),

    path('login/', login_view, name='login'),
    path('dashboard/', dashboard_view, name='dashboard'),

    # path('trigger-import/', trigger_import_view, name='trigger_import'),

    path('barcode-generator/', barcode_generator_view, name='barcode-generator-page'),  # renamed
    path('generate-barcode/', generate_barcode_view, name='generate-barcode'),

    path('api/generate-label/', generate_label_view, name='generate-label'),
    path('api/import-category/', import_category_view, name='import-category'),
    path('api/category-sheet-names/', category_sheet_names_view, name='category-sheet-names'),
    path('api/existing-categories/', existing_categories_view, name='existing-categories'),
    path('api/import-chunked/', import_chunked_view, name='import-chunked'),
    path('api/import-category-by-name/', import_category_by_name_view, name='import-by-name'),
    path('api/dashboard-stats/', dashboard_stats_view, name='dashboard-stats'),
]
