
from django.db.models import Q
from rest_framework import viewsets, filters
from .models import Category, Item
from .serializers import CategorySerializer, ItemSerializer
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import render
from django.core.management import call_command
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from .filters import ItemFilter
from django.contrib.auth.decorators import login_required

import barcode
from barcode.writer import ImageWriter
from barcode.errors import IllegalCharacterError, NumberOfDigitsError
from io import BytesIO
from django.http import HttpResponse
from django.template.loader import render_to_string

from rest_framework.pagination import PageNumberPagination

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows categories to be viewed.
    """
    queryset = Category.objects.all().order_by('id')
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated] 

class ItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows items to be viewed.
    This view manually handles filtering by category and searching by name/sku
    to ensure they work together correctly.
    """
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    
    # We still need the OrderingFilter for sorting!
    # We are removing DjangoFilterBackend and SearchFilter because we are handling them manually.
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['name', 'sku', 'created_at']
    ordering = ['-created_at']  # Default ordering: newest first
    
    def get_queryset(self):
        """
        This method is overridden to provide custom filtering logic.
        """
        # Start with all items.
        queryset = Item.objects.all()

        # 1. First, filter by category if a category ID is provided.
        category_id = self.request.query_params.get('category', None)
        if category_id:
            # This applies the filter, narrowing down the queryset.
            queryset = queryset.filter(category__id=category_id)

        # 2. Then, filter by the search term on the *already filtered* queryset.
        search_term = self.request.query_params.get('search', None)
        if search_term:
            # Use a Q object to search in EITHER the name OR the sku.
            # `icontains` makes the search case-insensitive.
            queryset = queryset.filter(
                Q(name__icontains=search_term)
            )
            
        # The OrderingFilter will be applied automatically by DRF after this method returns.
        # We can set a default order here.
        return queryset.order_by('name')

def login_view(request):
    """Serves the login.html template."""
    # Note: It seems counter-intuitive to protect a login page,
    # but it's good practice. If a user is already logged in and goes to /login/,
    # we can redirect them to the dashboard. Let's add that logic.
    from django.shortcuts import redirect
    if request.user.is_authenticated:
        return redirect('/dashboard/') # Redirect logged-in users away from login
    return render(request, 'core/login.html')

@login_required
def dashboard_view(request):
    """Serves the dashboard.html template after login."""
    return render(request, 'core/dashboard.html')

# --- NEW VIEW TO TRIGGER THE IMPORT SCRIPT ---
@api_view(['POST']) # Use POST for actions that change data or run processes
@permission_classes([IsAuthenticated]) # IMPORTANT: Only allow admins to run this
def trigger_import_view(request):
    """
    Triggers the 'import_inventory' management command.
    """
    try:
        # Show that the process is starting
        print("Import command triggered by user:", request.user.username)
        
        # Use call_command to run your script
        call_command('import_inventory')

        # Return a success response
        return JsonResponse({'status': 'success', 'message': 'Inventory synchronization completed successfully.'})

    except Exception as e:
        # Log the error and return an error response
        print(f"An error occurred during import: {e}")
        return JsonResponse({'status': 'error', 'message': f'An error occurred: {str(e)}'}, status=500)

@login_required
def barcode_generator_view(request):
    """Serves the barcode generator page."""
    return render(request, 'core/barcode_generator.html')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_barcode_view(request):
    """
    Generates a valid EAN-13 barcode image from a provided 13-digit SKU.
    It validates the SKU and uses it directly.
    """
    sku = request.GET.get('sku', None)
    if not sku:
        return Response({'error': 'SKU parameter is required.'}, status=400)

    # --- Step 1: Validate the SKU for EAN-13 rules ---
    # It MUST be a string of numbers, and its length must be exactly 13.
    if not sku.isdigit() or len(sku) != 13:
        error_message = f"Invalid SKU for EAN-13: '{sku}'. It must be a 13-digit number."
        return Response({'error': error_message}, status=400)

    try:
        # --- Step 2: Generate the barcode ---
        EAN = barcode.get_barcode_class('ean13')
        
        # We pass the full 13-digit SKU directly to the library.
        # The library will validate the checksum. If it's incorrect, it will raise an error.
        ean_barcode = EAN(sku, writer=ImageWriter())

        # Define rendering options for a clean look
        options = {
            'module_height': 15.0,
            'font_size': 10,
            'text_distance': 5.0,
            'quiet_zone': 3.0
        }

        # Write the barcode to an in-memory buffer
        buffer = BytesIO()
        ean_barcode.write(buffer, options=options)
        
        # --- Step 3: Return the image as a response ---
        buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type='image/png')

    except (IllegalCharacterError, NumberOfDigitsError) as e:
        # This will catch errors if the checksum is wrong or other library issues.
        error_message = f"Barcode generation failed for SKU '{sku}'. It may have an invalid checksum. Error: {e}"
        return Response({'error': error_message}, status=500)
    except Exception as e:
        # A fallback for any other unexpected errors
        error_message = f"An unexpected error occurred while generating the barcode for SKU '{sku}': {str(e)}"
        return Response({'error': error_message}, status=500)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_label_view(request):
    """
    Generates a full HTML document for a 30x20mm label,
    including company name, barcode, item name, and price.
    """
    sku = request.GET.get('sku', None)
    if not sku:
        return Response({'error': 'SKU parameter is required.'}, status=400)

    try:
        item = Item.objects.get(sku=sku)
    except Item.DoesNotExist:
        return Response({'error': f'Item with SKU {sku} not found.'}, status=404)

    # --- 1. Generate the barcode image data as Base64 ---
    # We'll embed the image directly into the HTML to avoid a separate request.
    try:
        # Prepare the 12-digit SKU for the library
        if not sku.isdigit() or len(sku) not in [12, 13]:
            raise ValueError("Invalid SKU for EAN-13.")
        
        sku_to_generate = sku[:12]
        
        EAN = barcode.get_barcode_class('ean13')
        ean_barcode = EAN(sku_to_generate, writer=ImageWriter())
        
        buffer = BytesIO()
        # Note: We are not rendering the text here, as we'll add it ourselves in the HTML
        ean_barcode.write(buffer, options={'write_text': False, 'module_height': 10.0})
        
        import base64
        barcode_image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
    except Exception as e:
        return Response({'error': f'Failed to generate barcode image: {e}'}, status=500)

    # --- 2. Prepare the context data for the template ---
    # This data will be passed into our new HTML template.
    context = {
        'company_name': 'ALOCADA ENTERPRISES',
        'item_name': item.name,
        'price': item.price,
        'sku': item.sku,
        'barcode_image_base64': barcode_image_base64,
    }

    # --- 3. Render the HTML template as a string ---
    # We will create 'core/label_template.html' in the next step.
    html_string = render_to_string('core/label_template.html', context)

    # --- 4. Return the full HTML document ---
    return HttpResponse(html_string)
