from rest_framework import serializers

from predictions.models import PredictionRun, ReorderRecommendation


class PredictionRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PredictionRun
        fields = "__all__"


class ReorderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)
    category = serializers.CharField(source="product.category.name", read_only=True, default=None)

    class Meta:
        model = ReorderRecommendation
        exclude = ["organization"]


class RefreshRequest(serializers.Serializer):
    batch_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class ReorderRequest(serializers.Serializer):
    product_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class RiskResultSerializer(serializers.Serializer):
    batch_id = serializers.IntegerField()
    risk_score = serializers.FloatField()
    risk_level = serializers.CharField()
    predicted_demand = serializers.FloatField(required=False, allow_null=True)
    expected_waste_qty = serializers.FloatField(required=False, allow_null=True)
    recommended_action = serializers.CharField(required=False, allow_blank=True)
    model = serializers.CharField(required=False)
    factors = serializers.DictField(required=False)


class RiskIngestRequest(serializers.Serializer):
    results = RiskResultSerializer(many=True)
