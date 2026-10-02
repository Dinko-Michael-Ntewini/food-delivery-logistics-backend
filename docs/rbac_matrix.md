# Final RBAC Responsibility Matrix

Final authentication and resource-scoped permissions are implemented. Restaurant owners need an active global OWNER membership; global STAFF/MANAGER memberships may manage catalogue but not staff or restaurant settings. Order, Payment, Refund, and Delivery visibility also permits active branch-scoped staff for their branch. Customer access is user-owned. `Own` means resources the actor owns or is assigned to.

| Capability | Admin | Restaurant owner | Staff | Customer | Driver |
|---|---|---|---|---|---|
| Manage restaurants | All | Own | — | — | — |
| Manage branches | All | Own | — | — | — |
| Manage staff | All | Own | — | — | — |
| Manage menus/categories/products | All | Own | Global manager membership | — | — |
| Use carts | — | — | — | Own | — |
| Place orders | — | — | — | Own | — |
| View orders | All | Active owned restaurant | Active restaurant/branch membership | Own | Via assigned Delivery only |
| Update order status | Valid steps; linked Delivery steps via Delivery API | Own restaurant preparation steps | Scoped preparation steps | — | Synchronized through assigned Delivery |
| View payments/refunds | All | Own restaurant | Active restaurant/branch membership | Own | — |
| Confirm/fail payments and create refunds | All | — | — | — | — |
| Manage drivers | All | — | — | — | Own driver profile only |
| Create Delivery / assign drivers | All | Own restaurant | Active restaurant/branch membership | — | — |
| View deliveries/history | All | Own restaurant | Active restaurant/branch membership | Own order | Assigned delivery |
| Update delivery status | Valid steps | — | — | — | Assigned delivery |
| Administer platform | Yes | — | — | — | — |

## Role notes

- `RESTAURANT_OWNER` is represented both by `User.role` and an active `RestaurantStaff.staff_role=OWNER` membership; the latter determines which restaurant is controlled.
- `STAFF` privileges are capability-scoped: global MANAGER membership for catalogue; active restaurant/branch membership for scoped order and dispatch operations.
- Customers can see only their own profile, addresses, carts, orders, payment status, refunds, and their order's delivery visibility.
- Drivers can update only deliveries assigned to their Driver record and should not change restaurant preparation states.
- Stage 7 uses an ADMIN-controlled internal simulation; production payment capture/refund execution would require provider-webhook and financial controls beyond this matrix.
- Stage 8 driver directory and profile creation are ADMIN-only. Drivers may update their own vehicle fields and availability, but cannot become unavailable while an active delivery exists. Restaurant dispatch uses known driver IDs; it grants no driver-profile management rights.
- Stage 8 reassignment is allowed only before pickup and appends an assignment audit note identifying old/new drivers. Physical delivery transitions require ADMIN or the currently assigned DRIVER.


POST /orders remains CUSTOMER-only. POST /payments resolves the existing initial payment and permits its CUSTOMER or ADMIN only; restaurant actors retain scoped financial GET access. POST /deliveries/{delivery_id}/assign-driver applies the same checks as PATCH /deliveries/{delivery_id}/assign. CUSTOMER profile/address/cart endpoints do not permit ADMIN impersonation.
