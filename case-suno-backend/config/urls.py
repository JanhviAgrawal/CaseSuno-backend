"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from .views import HealthCheckView, RootView

urlpatterns = [
    path('', RootView.as_view(), name='api-root'),
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls')),
    path('api/requirements/', include('customer_requirements.urls')),
    path('api/proposals/', include('proposals.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/matters/', include('matters.urls')),
    path('api/professionals/', include('professionals.urls')),
    path('api/documents/', include('documents.urls')),
    path('api/tasks/', include('tasks.urls')),
    path('api/audit/', include('audit.urls')),
    # API used by the casesuno.in website (Next.js server)
    path('api/web/', include('website.urls')),
]

admin.site.site_header = "CASE SUNO administration"
admin.site.site_title = "CASE SUNO admin"



