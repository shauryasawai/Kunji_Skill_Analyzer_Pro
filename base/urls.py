from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_jd, name='upload_jd'),
    path('results/<int:pk>/', views.results, name='results'),
    path('add-google-sheet/', views.add_google_sheet, name='add_google_sheet'),
    path('manage-google-sheets/', views.manage_google_sheets, name='manage_google_sheets'),
    path('sync-sheet/<int:sheet_pk>/', views.sync_google_sheet, name='sync_google_sheet'),
    path('match-candidates/<int:jd_pk>/', views.match_candidates, name='match_candidates'),
    path('show-matches/<int:jd_pk>/', views.show_matches, name='show_matches'),
]