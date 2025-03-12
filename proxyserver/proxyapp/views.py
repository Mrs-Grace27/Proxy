from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import requests
import logging
import re
import json
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote
from .models import Song

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of hop-by-hop headers that should not be forwarded
HOP_BY_HOP_HEADERS = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'content-encoding',
    'content-length'
}

@csrf_exempt
def proxy_request(request, path=''):
    """
    Acts as a forward proxy for the Chrome extension
    """
    # Get the target URL from the query parameter
    target_url = request.GET.get("url")
   
    if not target_url:
        return JsonResponse({"error": "No URL provided"}, status=400)
   
    # Construct the full URL if path is provided
    if path:
        if not target_url.endswith('/'):
            target_url += '/'
        url = f"{target_url}{path}"
    else:
        url = target_url
   
    # Get the proxy base URL for rewriting
    proxy_base = request.build_absolute_uri('/').rstrip('/')
    proxy_path = request.path.rstrip('/')
    if proxy_path:
        proxy_base = proxy_base + proxy_path
   
    # Log the request
    logger.info(f"Proxying {request.method} request to: {url}")
   
    # Forward all headers except 'host' and hop-by-hop headers
    headers = {key: value for key, value in request.headers.items()
               if key.lower() not in ['host'] and key.lower() not in HOP_BY_HOP_HEADERS}
   
    # Add a User-Agent if not present
    if 'user-agent' not in [k.lower() for k in headers.keys()]:
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
   
    # Get request body for appropriate methods
    data = request.body if request.method in ["POST", "PUT", "PATCH"] else None
   
    try:
        # Make the request to the target URL
        response = requests.request(
            method=request.method,
            url=url,
            headers=headers,
            params={k: v for k, v in request.GET.items() if k != 'url'},
            data=data,
            cookies=request.COOKIES,
            stream=True,  # Use streaming for all content types
            timeout=30,
            allow_redirects=False  # Handle redirects manually
        )
        
        # Handle redirects manually to ensure they go through the proxy
        if response.status_code in [301, 302, 303, 307, 308]:
            redirect_url = response.headers.get('Location')
            if redirect_url:
                # Make the redirect URL absolute if it's relative
                if not redirect_url.startswith(('http://', 'https://')):
                    redirect_url = urljoin(url, redirect_url)
                
                # Rewrite the redirect to go through our proxy
                proxy_redirect = f"{proxy_base}?url={quote(redirect_url)}"
                
                # Create a response with the new location
                redirect_response = HttpResponse(status=response.status_code)
                redirect_response['Location'] = proxy_redirect
                
                # Copy any other headers
                for key, value in response.headers.items():
                    if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != 'location':
                        redirect_response[key] = value
                
                return redirect_response
       
        content_type = response.headers.get('Content-Type', '')
        
        # Process HTML content to rewrite URLs
        if 'text/html' in content_type.lower():
            content = response.content.decode('utf-8', errors='replace')
            soup = BeautifulSoup(content, 'html.parser')
            
            # Parse the URL to get the base for relative URLs
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Fix relative URLs in various elements
            for tag in soup.find_all(['link', 'script', 'img', 'a', 'form', 'iframe']):
                # Handle different attributes based on tag type
                attr_map = {
                    'link': 'href',
                    'script': 'src',
                    'img': 'src',
                    'a': 'href',
                    'form': 'action',
                    'iframe': 'src'
                }
                
                attr = attr_map.get(tag.name)
                if attr and tag.has_attr(attr):
                    url_value = tag[attr]
                    # Skip empty values, anchors, javascript and data URIs
                    if not url_value or url_value.startswith(('javascript:', 'data:', 'mailto:', '#')):
                        continue
                    
                    # Make URL absolute
                    if not url_value.startswith(('http://', 'https://', '//')):
                        absolute_url = urljoin(url, url_value)
                    elif url_value.startswith('//'):
                        absolute_url = f"{parsed_url.scheme}:{url_value}"
                    elif url_value.startswith('/'):
                        absolute_url = urljoin(base_url, url_value)
                    else:
                        absolute_url = url_value
                    
                    # Rewrite as a proxied URL
                    tag[attr] = f"{proxy_base}?url={quote(absolute_url)}"
            
            # Fix CSS imports and url() references in style tags
            for style in soup.find_all('style'):
                if style.string:
                    style.string = re.sub(
                        r'url\([\'"]?(?!data:|http:|https:)([^\)]+)[\'"]?\)',
                        lambda m: f'url("{proxy_base}?url={quote(urljoin(url, m.group(1)))}")',
                        style.string
                    )
            
            # Handle base tag
            base_tags = soup.find_all('base')
            for base_tag in base_tags:
                if base_tag.has_attr('href'):
                    # Update base URL for the page
                    base_href = base_tag['href']
                    base_url = urljoin(url, base_href)
                    # Remove the base tag as it will interfere with our URL rewriting
                    base_tag.decompose()
            
            # Inject a small script to handle dynamic URL loading
            script_tag = soup.new_tag('script')
            script_tag.string = """
            (function() {
                // Intercept fetch requests
                const originalFetch = window.fetch;
                window.fetch = function(resource, init) {
                    if (typeof resource === 'string') {
                        // Make the URL absolute
                        const absoluteUrl = new URL(resource, window.location.href).href;
                        // If it's not already proxied, proxy it
                        if (!absoluteUrl.includes('/proxy?url=')) {
                            resource = window.location.origin + '/proxy?url=' + encodeURIComponent(absoluteUrl);
                        }
                    }
                    return originalFetch.apply(this, arguments);
                };
                
                // Intercept XMLHttpRequest
                const originalOpen = XMLHttpRequest.prototype.open;
                XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
                    if (typeof url === 'string') {
                        // Make the URL absolute
                        const absoluteUrl = new URL(url, window.location.href).href;
                        // If it's not already proxied, proxy it
                        if (!absoluteUrl.includes('/proxy?url=')) {
                            url = window.location.origin + '/proxy?url=' + encodeURIComponent(absoluteUrl);
                        }
                    }
                    return originalOpen.call(this, method, url, async, user, password);
                };
            })();
            """
            soup.head.append(script_tag)
            
            content = str(soup)
            response_obj = HttpResponse(
                content=content,
                content_type=content_type
            )
        
        # Handle CSS files
        elif 'text/css' in content_type.lower() or url.endswith('.css'):
            content = response.content.decode('utf-8', errors='replace')
            # Fix relative URLs in CSS
            content = re.sub(
                r'url\([\'"]?(?!data:|http:|https:)([^\)]+)[\'"]?\)',
                lambda m: f'url("{proxy_base}?url={quote(urljoin(url, m.group(1)))}")',
                content
            )
            # Fix import statements
            content = re.sub(
                r'@import\s+[\'"](?!data:|http:|https:)([^\'"]+)[\'"]',
                lambda m: f'@import "{proxy_base}?url={quote(urljoin(url, m.group(1)))}"',
                content
            )
            response_obj = HttpResponse(
                content=content,
                content_type='text/css'
            )
        
        # Special handling for JavaScript
        elif 'javascript' in content_type.lower() or url.endswith('.js'):
            content = response.content.decode('utf-8', errors='replace')
            # We could potentially rewrite URLs in JavaScript, but it's complex and error-prone
            # For now, just return the JS as-is
            response_obj = HttpResponse(
                content=content,
                content_type='application/javascript'
            )
        
        # For all other content types, stream as-is
        else:
            response_obj = StreamingHttpResponse(
                streaming_content=response.iter_content(chunk_size=8192),
                content_type=content_type
            )
        
        # Copy status code
        response_obj.status_code = response.status_code
        
        # Copy headers, excluding hop-by-hop headers
        for key, value in response.headers.items():
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != 'content-length':
                response_obj[key] = value
        
        # Add CORS headers to allow the extension to work properly
        response_obj['Access-Control-Allow-Origin'] = '*'
        response_obj['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
        response_obj['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        
        logger.info(f"Proxy response for {url}: status {response.status_code}")
        return response_obj
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error proxying request to {url}: {str(e)}")
        return JsonResponse({"error": str(e), "url": url}, status=500)
    except Exception as e:
        logger.error(f"Unexpected error for {url}: {str(e)}")
        return JsonResponse({"error": f"Unexpected error: {str(e)}", "url": url}, status=500)

@csrf_exempt
def options(request):
    """Handle CORS preflight requests"""
    response = HttpResponse()
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@csrf_exempt
def proxy_info(request):
    """Return information about the proxy server"""
    return JsonResponse({
        "status": "active",
        "server_location": "UK",
        "version": "1.0"
    })
   
@csrf_exempt
def test(request):
    return JsonResponse({"message": "Hello, World!"})

@csrf_exempt
def mark(request):
    """
    Mark a video as watched
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    # Get the video ID from the request body
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    category = data.get('category')
    video_id = data.get('videoId')
    if not video_id:
        return JsonResponse({"error": "No video ID provided"}, status=400)
    
    # Check if the video is already marked
    if Song.objects.filter(videoId=video_id).exists() and category != 'Fav':
        return JsonResponse({"message": "Video already marked!"}, status=200)
    
    # Save the video to the database
    song = Song(
        channelName=data.get('channelName'),
        currentTime=data.get('currentTime'),
        duration=data.get('duration'),
        savedAt=data.get('savedAt'),
        title=data.get('title'),
        url=data.get('url'),
        videoId=video_id,
        category=data.get('category')
    )
    song.save()
    
    return JsonResponse({"message": "Video marked successfully!"}, status=200)

@csrf_exempt
def export_songs_csv(request):
    """
    Export all songs as a CSV file using pandas
    """
    # Query all songs from the database
    songs = Song.objects.all().values(
        'id', 
        'channelName', 
        'currentTime', 
        'duration', 
        'savedAt', 
        'title', 
        'url', 
        'videoId', 
        'category'
    )
    
    # Convert queryset to pandas DataFrame
    df = pd.DataFrame(list(songs))
    
    # Create HTTP response with CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="songs.csv"'
    
    # Write DataFrame to CSV
    df.to_csv(response, index=False)
    
    return response