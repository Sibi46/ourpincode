from django.urls import path
from . import views

urlpatterns = [
    path('admin/lucky-draws/', views.admin_lucky_draws, name='opc_admin_lucky_draws'),
    # ── Admin ─────────────────────────────────────────────────────────────────
    path('admin/',                              views.admin_dashboard,          name='opc_admin_dashboard'),
    path('admin/salesmen/',                     views.admin_salesmen,           name='opc_admin_salesmen'),
    path('admin/salesmen/create/',              views.admin_salesman_create,    name='opc_admin_salesman_create'),
    path('admin/salesmen/<int:pk>/',            views.admin_salesman_detail,    name='opc_admin_salesman_detail'),
    path('admin/shops/',                        views.admin_shops,              name='opc_admin_shops'),
    path('admin/coupons/',                      views.admin_coupons,            name='opc_admin_coupons'),
    path('admin/coupon-audit/',                 views.admin_coupon_audit,       name='opc_admin_coupon_audit'),
    path('admin/rewards/',                      views.admin_rewards,            name='opc_admin_rewards'),
    path('admin/rewards/create/',               views.admin_reward_create,      name='opc_admin_reward_create'),
    path('admin/rewards/<int:pk>/edit/',        views.admin_reward_edit,        name='opc_admin_reward_edit'),
    path('admin/spinwheel/',                    views.admin_spinwheel,          name='opc_admin_spinwheel'),
    path('admin/customers/',                    views.admin_customers,          name='opc_admin_customers'),
    path('admin/redemptions/',                  views.admin_redemptions,        name='opc_admin_redemptions'),

    # ── Salesman ──────────────────────────────────────────────────────────────
    path('salesman/login/',                     views.salesman_login,           name='opc_salesman_login'),
    path('salesman/logout/',                    views.salesman_logout,          name='opc_salesman_logout'),
    path('salesman/',                           views.salesman_dashboard,       name='opc_salesman_dashboard'),
    path('salesman/shops/',                     views.salesman_shops,           name='opc_salesman_shops'),
    path('salesman/shops/new/',                 views.salesman_shop_create,     name='opc_salesman_shop_create'),
    path('salesman/shops/<int:pk>/',            views.salesman_shop_detail,     name='opc_salesman_shop_detail'),
    path('salesman/give-coupons/',              views.salesman_give_coupons,    name='opc_salesman_give_coupons'),
    path('salesman/shops/add-from-biz/',        views.salesman_add_shop_from_biz, name='opc_salesman_add_shop_from_biz'),
    path('salesman/coupon-history/',            views.salesman_coupon_history,  name='opc_salesman_coupon_history'),

    # ── Customer ──────────────────────────────────────────────────────────────
    path('activate/',                           views.customer_activate_coupon, name='opc_activate_coupon'),
    path('spin/',                               views.customer_spin_wheel,      name='opc_spin_wheel'),
    path('api/spin/',                           views.customer_spin_api,        name='opc_spin_api'),
    path('my-points/',                          views.customer_my_points,       name='opc_my_points'),
    path('rewards/',                            views.customer_rewards,         name='opc_rewards'),
    path('rewards/<int:pk>/redeem/',            views.customer_redeem,          name='opc_redeem'),
    path('redemptions/<int:pk>/success/',       views.customer_redemption_success, name='opc_redemption_success'),
    path('my-redemptions/',                     views.customer_my_redemptions,  name='opc_my_redemptions'),

    # ── Shop ──────────────────────────────────────────────────────────────────
    path('verify/',                             views.shop_verify_redemption,   name='opc_verify_redemption'),
]
