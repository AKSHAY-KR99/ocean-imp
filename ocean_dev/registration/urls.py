from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'user', views.UserModelViewSet)
router.register(r'userdetail', views.UserDetailModelViewSet)
router.register(r'onboard/email', views.OnBoardEmailAPI)

urlpatterns = [
    path('login/', views.UserLoginView.as_view(), name="user_login"),
    path('password/set/', views.UserPasswordSetView.as_view(), name="user_set_password"),
    path('otp/validate/', views.OtpValidationView.as_view(), name="user_otp_validation"),
    path('token/generate/', views.UserAuthTokenGenerationView.as_view(), name="generate_auth_token"),
    path('slug/<slug:slug_value>/', views.UserDetailBySlug.as_view(), name="user_detail_slug"),
    path('activate/user/', views.ActivatingUserView.as_view(), name="activate_user"),
    #path('logout/', views.LogoutView.as_view(), name="user_logout"),
    path('detail/user/', views.LoggedInUserDetail.as_view(), name="logged_in_user_detail"),
    path('generate/onboard/template/data/', views.GenerateOnboardTemplateData.as_view(), name="generate_template_data"),
    path('send/sme/data/', views.ReviewUserMailView.as_view(), name="send_sme_data"),
    path('delete/user/<int:user_id>/', views.DeleteUser.as_view(), name="delete_user"),
    path('reactivate/user/<int:user_id>/', views.UserReactivateAPI.as_view(), name='reactivate_deleted_user'),
    path('xero/auth-url/', views.XeroAuthUrlAPI.as_view(), name='xero_auth_url'),
    # path('xero/callback/', views.XeroCallbackAPI.as_view(), name='xero_callback'),
    path('token/', views.XeroTokenAPI.as_view(), name='xero_token'),
    path('xero/response/', views.XeroResponse.as_view(), name='xero_response'),
    path('onboard/update/<int:user_id>/', views.OnBoardDataAPI.as_view(), name='onboard_update'),
    # path('onboard/email/', views.OnBoardEmailAPI.as_view(), name='onboard_email'),
    path('sme/review/mail/', views.SMEOnboardReviewMailListAPI.as_view(), name='sme_review_mail_listing'),
    path('codat/response/', views.CodatResponseAPI.as_view(), name='codat_response'),
    path('password/reset/', views.UserPasswordResetView.as_view(), name="user_reset_password"),
    path('disconnect/codat/', views.CodatDisconnectView.as_view(), name="codat_disconnect"),
    path('user/logout/', views.LogoutView.as_view(), name="user_logout"),
    path('codat/visualize/', views.CodatVisualizeView.as_view(), name="codat_visualize"),
    path('codat/status/', views.CodatStatus.as_view(), name="codat_status"),
    path('', include(router.urls)),
]
