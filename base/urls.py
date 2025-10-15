from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_jd, name='upload_jd'),
    path('results/<int:pk>/', views.results, name='results'),
]