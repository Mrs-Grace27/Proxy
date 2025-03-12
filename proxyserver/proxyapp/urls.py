# from django.urls import path, re_path

# from . import views

# urlpatterns = [
#     path('proxy/', views.proxy_request, name='proxy'),
#     # re_path(r'^(?P<path>.*)$', views.proxy_request, name='proxy_with_path'),
#     path("test/", views.test, name='test_request'),
# ]

from django.urls import path, re_path
from . import views

urlpatterns = [
    path('proxy', views.proxy_request, name='proxy'),
    path('proxy/', views.proxy_request, name='proxy_root'),
    path('proxy/info', views.proxy_info, name='proxy_info'),
    re_path(r'^proxy/(.*)$', views.proxy_request, name='proxy_path'),
    path('test', views.test, name='test'),
    path('options', views.options, name='options'),
    path('mark/', views.mark, name='mark-video'),
    path('export-songs/', views.export_songs_csv, name='export_songs_csv'),
]