from django.contrib import admin
from .models import UploadBatch, UploadRow

admin.site.register([UploadBatch, UploadRow])
