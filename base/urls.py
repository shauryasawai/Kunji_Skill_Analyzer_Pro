from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_jd, name='upload_jd'),
    path('results/<int:pk>/', views.results, name='results'),
    path('upload-database/', views.upload_candidate_database, name='upload_candidate_database'),
    path('manage-databases/', views.manage_databases, name='manage_databases'),
    path('match-candidates/<int:jd_pk>/', views.match_candidates, name='match_candidates'),
    path('show-matches/<int:jd_pk>/', views.show_matches, name='show_matches'),
]