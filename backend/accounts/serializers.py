from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", "phone", "location", "role", "is_active"]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        user = authenticate(email=attrs["email"].lower(), password=attrs["password"])
        if not user or not user.is_active:
            raise serializers.ValidationError("Invalid email or password.")
        attrs["user"] = user
        return attrs


class TeamMemberSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=6)

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", "phone", "location", "role", "is_active", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        role = validated_data.get("role") or self.context.get("role") or User.Role.CRE
        return User.objects.create_user(password=password, **validated_data)

    def validate(self, attrs):
        role = attrs.get("role") or self.context.get("role") or getattr(self.instance, "role", User.Role.CRE)
        if role == User.Role.SALES_MANAGER and not (attrs.get("location") or getattr(self.instance, "location", "")).strip():
            raise serializers.ValidationError({"location": "Choose the manager branch."})
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


SalesOfficerSerializer = TeamMemberSerializer
