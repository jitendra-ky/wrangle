"""
URL configuration for the zserver app.

All routes are mounted at the project level (zproject/urls.py)
under the root prefix, so these paths are exactly as the assignment specifies:

    POST   /jobs/upload
    GET    /jobs/
    GET    /jobs/<job_id>/status
    GET    /jobs/<job_id>/results
"""

from django.urls import path

from . import views

app_name = "zserver"

urlpatterns = [
    path("jobs/upload",             views.upload_job,   name="job-upload"),
    path("jobs/",                   views.list_jobs,    name="job-list"),
    path("jobs/<int:job_id>/status",  views.job_status,   name="job-status"),
    path("jobs/<int:job_id>/results", views.job_results,  name="job-results"),
]
