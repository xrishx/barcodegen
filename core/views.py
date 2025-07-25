from django.db.models import Q
from rest_framework import viewsets, filters
from .models import Category, Item, DashboardStats
from .serializers import CategorySerializer, ItemSerializer
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import render, redirect
from django.core.management import call_command
from django.http import JsonResponse, HttpResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from .filters import ItemFilter
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
import barcode
from barcode.writer import ImageWriter
from barcode.errors import IllegalCharacterError, NumberOfDigitsError
from io import BytesIO
from django.template.loader import render_to_string
from django.contrib.auth import authenticate, login
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination

from google.oauth2.service_account import Credentials
import gspread
from django.conf import settings

from core.utils.import_helpers import import_category_from_sheet, update_dashboard_stats
import logging
import json


logger = logging.getLogger(__name__)

# --- ViewSets ---

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all().order_by('id')
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]


class ItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    An optimized ViewSet for Items that uses DRF's built-in
    filtering and searching for maximum performance.
    """
    queryset = Item.objects.all().select_related('category') # .select_related is a performance boost
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    # This is the corrected list of backends
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]

    # --- Configuration for the filter backends ---

    # 1. For SearchFilter: Tells it which fields to search within
    search_fields = ['name', 'sku']

    # 2. For DjangoFilterBackend: Tells it which fields we can filter by exact match
    filterset_fields = ['category']

    # 3. For OrderingFilter: This remains the same
    ordering_fields = ['name', 'sku', 'created_at']
    ordering = ['-created_at'] # Default sort order

    # NOTE: The custom get_queryset() method is no longer needed and has been removed.


# --- Authentication views ---

def login_view(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get('next') or '/dashboard/')
        else:
            return render(request, 'core/login.html', {'error': 'Invalid username or password.'})

    return render(request, 'core/login.html')


@login_required
def dashboard_view(request):
    print(f"User authenticated? {request.user.is_authenticated}, user: {request.user}")
    return render(request, 'core/dashboard.html')


@login_required
def barcode_generator_view(request):
    return render(request, 'core/barcode_generator.html')


# --- Barcode generation ---

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_barcode_view(request):
    sku = request.GET.get('sku')
    if not sku:
        return Response({'error': 'SKU parameter is required.'}, status=400)

    if not sku.isdigit() or len(sku) != 13:
        return Response({'error': 'SKU must be a 13-digit number.'}, status=400)

    try:
        EAN = barcode.get_barcode_class('ean13')
        ean_barcode = EAN(sku, writer=ImageWriter())
        options = {
            'module_height': 15.0,
            'font_size': 10,
            'text_distance': 5.0,
            'quiet_zone': 3.0
        }
        buffer = BytesIO()
        ean_barcode.write(buffer, options=options)
        buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type='image/png')
    except (IllegalCharacterError, NumberOfDigitsError) as e:
        return Response({'error': f'Invalid SKU or checksum error: {e}'}, status=500)
    except Exception as e:
        return Response({'error': f'Unexpected error generating barcode: {e}'}, status=500)


# --- Label generation (HTML with client-side JsBarcode) ---

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generate_label_view(request):
    sku = request.GET.get('sku')
    if not sku:
        return Response({'error': 'SKU parameter is required.'}, status=400)

    if not sku.isdigit() or len(sku) != 13:
        return Response({'error': 'SKU must be a 13-digit number.'}, status=400)

    try:
        item = Item.objects.get(sku=sku)
    except Item.DoesNotExist:
        return Response({'error': f'Item with SKU {sku} not found.'}, status=404)
    except Exception as e:
        return Response({'error': f'Database error: {e}'}, status=500)

    context = {
        'company_name': 'ALOCADA ENTERPRISES',
        'item_name': item.name,
        'price': item.price,
        'sku': item.sku,
    }

    try:
        html_string = render_to_string('core/label_template.html', context)
        return HttpResponse(html_string)
    except Exception as e:
        return Response({'error': f'Error rendering label template: {e}'}, status=500)


# --- Google Sheets import views ---

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_category_view(request):
    category_name = request.data.get('category_name')
    if not category_name:
        return Response({"error": "Missing category_name"}, status=400)

    if not Category.objects.filter(name=category_name).exists():
        return Response({"error": f"Category '{category_name}' does not exist."}, status=400)

    scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_info(settings.GOOGLE_SHEETS_CREDENTIALS, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open('MASTER LIST 2 - v2.updated one')

    try:
        sheet = spreadsheet.worksheet(category_name)
    except gspread.WorksheetNotFound:
        return Response({"error": f"No sheet named '{category_name}' found."}, status=404)

    try:
        summary = import_category_from_sheet(sheet, settings.GOOGLE_SHEETS_CREDENTIALS)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

    return Response({
        "updated": True,
        "category_name": summary["category_name"],
        "items_processed": summary["items_processed"],
        "message": summary["message"],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def existing_categories_view(request):
    categories = Category.objects.all().values_list('name', flat=True)
    return Response({'categories': list(categories)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def category_sheet_names_view(request):
    try:
        scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_info(settings.GOOGLE_SHEETS_CREDENTIALS, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open('MASTER LIST 2 - v2.updated one')

        # Skip first 4 sheets as requested
        category_sheets = spreadsheet.worksheets()[4:]
        names = [sheet.title for sheet in category_sheets]
        return Response({'names': names})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_chunked_view(request):
    category_index = request.data.get('category_index', 0)

    try:
        scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_info(settings.GOOGLE_SHEETS_CREDENTIALS, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open('MASTER LIST 2 - v2.updated one')

        category_sheets = spreadsheet.worksheets()[4:]

        if category_index >= len(category_sheets):
            return Response({
                'done': True,
                'message': 'All categories have been synchronized!'
            })

        sheet_to_import = category_sheets[category_index]
        summary = import_category_from_sheet(sheet_to_import, settings.GOOGLE_SHEETS_CREDENTIALS)

        return Response({
            'done': False,
            'message': summary.get('message', f"Processed sheet '{sheet_to_import.title}'."),
            'next_category_index': category_index + 1
        })

    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API error during import: {e}")
        return Response({'error': 'Google Sheets API error. Check rate limits/permissions.'}, status=503)
    except Exception as e:
        logger.error(f"Unexpected error during chunked import at index {category_index}: {e}")
        return Response({'error': f'Unexpected error: {str(e)}'}, status=500)

# Add this new view function to your core/views.py file

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_category_by_name_view(request):
    category_name = request.data.get('category_name')
    if not category_name:
        return Response({"error": "Missing 'category_name' in request."}, status=400)

    try:
        scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_info(settings.GOOGLE_SHEETS_CREDENTIALS, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open('MASTER LIST 2 - v2.updated one')

        # This is the efficient part: get the worksheet directly by name
        sheet_to_import = spreadsheet.worksheet(category_name)
        
        summary = import_category_from_sheet(sheet_to_import, settings.GOOGLE_SHEETS_CREDENTIALS)

        return Response({
            "message": summary.get('message', f"Processed sheet '{category_name}'.")
        })

    except gspread.WorksheetNotFound:
        logger.error(f"Worksheet '{category_name}' not found in Google Sheets.")
        return Response({'error': f"Worksheet '{category_name}' not found."}, status=404)
    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API error while importing '{category_name}': {e}")
        return Response({'error': 'Google Sheets API error. Check rate limits/permissions.'}, status=503)
    except Exception as e:
        logger.error(f"Unexpected error while importing '{category_name}': {e}")
        return Response({'error': f'An unexpected error occurred: {str(e)}'}, status=500)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats_view(request):
    """
    Provides dashboard stats instantly by reading from the pre-calculated table.
    If the stats are zero, it triggers a one-time recalculation.
    """
    stats, created = DashboardStats.objects.get_or_create(id=1)
    
    # "Prime the pump": If the stats are zero (likely because this is the first run),
    # and it's not a newly created row, trigger a one-time update.
    # We also check if there are actually items in the DB, to avoid recounting an empty db.
    if not created and stats.total_items == 0 and Item.objects.exists():
        update_dashboard_stats()
        # Refresh the stats object from the database after updating it
        stats = DashboardStats.objects.get(id=1)

    user_data = {'username': request.user.username} if request.user.is_authenticated else {}
    
    data = {
        'total_items': stats.total_items,
        'total_categories': stats.total_categories,
        'user': user_data
    }
    return Response(data)

def batch_generate_labels_view(request):
    """
    Receives a list of SKUs and returns a dictionary of
    { sku: rendered_html, ... }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        # Load the list of SKUs from the request body
        data = json.loads(request.body)
        skus = data.get('skus', [])
        
        if not isinstance(skus, list):
            return JsonResponse({'error': 'SKUs must be a list'}, status=400)

        # Fetch the corresponding items from the database in a single query
        items = Item.objects.filter(sku__in=skus)
        
        # Create a dictionary for quick lookups
        items_by_sku = {item.sku: item for item in items}
        
        labels_html = {}
        company_name = "ALOCADA ENTERPRISES" # Or get this from settings/DB

        # Loop through the requested SKUs to generate HTML for each
        for sku in skus:
            item = items_by_sku.get(sku)
            if item:
                context = {
                    'sku': item.sku,
                    'item_name': item.name,
                    'price': item.price,
                    'company_name': company_name,
                }
                # Use the exact same template as your single-label API
                html = render_to_string('core/label_template.html', context)
                labels_html[sku] = html
        
        return JsonResponse(labels_html)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)