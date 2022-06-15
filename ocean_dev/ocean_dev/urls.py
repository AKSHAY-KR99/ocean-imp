"""ocean_dev URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.permissions import AllowAny
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from registration import views

schema_view = get_schema_view(
    openapi.Info(
        title="Ocean Dev API",
        default_version='v1',
        description="Ocean Dev API details"
    ),
    public=True,
    permission_classes=(AllowAny,),
)

urlpatterns = [
    path('doc/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('ocean/admin/', admin.site.urls),
    # path('sme-onboard/', views.XeroCallbackAPI.as_view(), name='xero_callback'),
    path('account/', include('registration.urls')),
    path('contacts/', include('contact_app.urls')),
    path('transactions/', include('transaction_app.urls')),
    path('dashboard/', include('dashboard_app.urls'))
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
