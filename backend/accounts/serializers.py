from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    lifecycle_status = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", "phone", "location", "role", "is_active", "deleted_at", "lifecycle_status"]


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
    lifecycle_status = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", "phone", "location", "role", "is_active", "deleted_at", "lifecycle_status", "password"]
        read_only_fields = ["is_active", "deleted_at", "lifecycle_status"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        role = self.context.get("role") or validated_data.get("role") or User.Role.CRE
        validated_data["role"] = role
        return User.objects.create_user(password=password, **validated_data)

    def validate(self, attrs):
        role = self.context.get("role") or attrs.get("role") or getattr(self.instance, "role", User.Role.CRE)
        if self.instance and "role" in attrs and attrs["role"] != self.instance.role:
            raise serializers.ValidationError({"role": "Create a new account instead of changing an employee's role."})
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
