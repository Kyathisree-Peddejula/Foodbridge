from django.contrib import admin

from predictions.models import PredictionRun, ReorderRecommendation

admin.site.register([PredictionRun, ReorderRecommendation])
