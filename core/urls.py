from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ItemViewSet, login_view, dashboard_view, trigger_import_view, barcode_generator_view, generate_barcode_view, generate_label_view


# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'inventory/categories', CategoryViewSet, basename='category')
router.register(r'inventory/items', ItemViewSet, basename='item')

# The API URLs are now determined automatically by the router.
urlpatterns = [
    path('', include(router.urls)),

    path('login/', login_view, name='login'),
    path('dashboard/', dashboard_view, name='dashboard'),

    path('trigger-import/', trigger_import_view, name='trigger_import'),
    path('barcode-generator/', barcode_generator_view, name='generate-barcode'),   
    path('generate-barcode/', generate_barcode_view, name='generate-barcode'), 
    path('api/generate-label/', generate_label_view, name='generate-label'),
]