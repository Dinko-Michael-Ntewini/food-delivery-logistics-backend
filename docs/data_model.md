# Data Model

Conventions: `UUID` primary keys; `TS` = UTC timestamp; `FK` names its target; `R`/`O` mean required/optional. Every mutable operational entity has `created_at` and `updated_at` (`TS`, R); immutable history rows have `created_at` only.

## Identity and customer

### 1. User — `users`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| email | VARCHAR(254) | No | Yes | — | normalized login/email |
| password_hash | VARCHAR(255) | No | No | — | credential hash only |
| full_name | VARCHAR(150) | No | No | — | display/legal name |
| phone | VARCHAR(32) | Yes | Yes | — | contact number |
| role | UserRole enum | No | No | — | ADMIN, RESTAURANT_OWNER, STAFF, CUSTOMER, DRIVER |
| is_active | BOOLEAN | No | No | — | account availability |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 2. Address — `addresses`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| user_id | UUID | No | No | users.id | owning customer |
| label | VARCHAR(60) | No | No | — | e.g. Home |
| recipient_name, recipient_phone | VARCHAR | No | No | — | delivery contact |
| line1 | VARCHAR(180) | No | No | — | street/location |
| line2, landmark | VARCHAR | Yes | No | — | supplementary directions |
| city | VARCHAR(100) | No | No | — | locality |
| latitude, longitude | DECIMAL(9,6) | Yes | No | — | delivery/search coordinates |
| is_default | BOOLEAN | No | No | — | preferred address |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 3. CustomerProfile — `customer_profiles`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| user_id | UUID | No | Yes | users.id | customer identity (1:1) |
| preferred_contact_method | ContactMethod enum | Yes | No | — | contact preference |
| marketing_opt_in | BOOLEAN | No | No | — | consent flag |
| created_at, updated_at | TS | No | No | — | audit timestamps |

## Restaurant catalogue

### 4. Restaurant — `restaurants`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| name | VARCHAR(160) | No | No | — | trading name |
| slug | VARCHAR(180) | No | Yes | — | URL/search identity |
| contact_email, contact_phone | VARCHAR | Yes | No | — | business contacts |
| description | TEXT | Yes | No | — | public description |
| is_active | BOOLEAN | No | No | — | platform availability |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 5. RestaurantBranch — `restaurant_branches`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| restaurant_id | UUID | No | No | restaurants.id | parent restaurant |
| name | VARCHAR(120) | No | No | — | branch identity |
| phone, email | VARCHAR | Yes | No | — | branch contact |
| line1, city | VARCHAR | No | No | — | fulfilment location |
| latitude, longitude | DECIMAL(9,6) | Yes | No | — | location filtering |
| is_active | BOOLEAN | No | No | — | orderability |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 6. RestaurantStaff — `restaurant_staff`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | membership primary key |
| restaurant_id | UUID | No | No | restaurants.id | employer |
| user_id | UUID | No | No | users.id | staff/owner user |
| branch_id | UUID | Yes | No | restaurant_branches.id | optional branch scope |
| staff_role | RestaurantStaffRole enum | No | No | — | OWNER, MANAGER, STAFF |
| is_active | BOOLEAN | No | No | — | membership status |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 7. Menu — `menus`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| restaurant_id | UUID | No | No | restaurants.id | catalogue owner |
| name | VARCHAR(120) | No | No | — | menu name |
| description | TEXT | Yes | No | — | public detail |
| is_active | BOOLEAN | No | No | — | publication state |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 8. Category — `categories`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| menu_id | UUID | No | No | menus.id | parent menu |
| name | VARCHAR(100) | No | No | — | category name |
| description | TEXT | Yes | No | — | explanatory text |
| display_order | INTEGER | No | No | — | UI order |
| is_active | BOOLEAN | No | No | — | visibility |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 9. Product — `products`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| category_id | UUID | No | No | categories.id | parent category |
| name | VARCHAR(160) | No | No | — | item name |
| description | TEXT | Yes | No | — | detail |
| base_price | DECIMAL(12,2) | No | No | — | price when no variant override |
| is_available | BOOLEAN | No | No | — | can be ordered |
| image_url | VARCHAR(2048) | Yes | No | — | media reference |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 10. ProductVariant — `product_variants`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| product_id | UUID | No | No | products.id | parent product |
| name | VARCHAR(120) | No | No | — | e.g. Large |
| sku | VARCHAR(80) | Yes | Yes | — | stock/integration key |
| price_override | DECIMAL(12,2) | Yes | No | — | replaces base price if present |
| price_delta | DECIMAL(12,2) | Yes | No | — | alternative additive adjustment; mutually exclusive with override |
| is_available | BOOLEAN | No | No | — | availability |
| created_at, updated_at | TS | No | No | — | audit timestamps |

## Ordering

### 11. Cart — `carts`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| customer_id | UUID | No | No | customer_profiles.id | cart owner |
| branch_id | UUID | Yes | No | restaurant_branches.id | null while empty; first item selects a branch |
| status | CartStatus enum | No | No | — | ACTIVE or CHECKED_OUT |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 12. CartItem — `cart_items`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| cart_id | UUID | No | No | carts.id | parent cart |
| product_id | UUID | No | No | products.id | chosen product |
| product_variant_id | UUID | Yes | No | product_variants.id | optional chosen variant |
| quantity | INTEGER | No | No | — | positive item count |
| notes | VARCHAR(500) | Yes | No | — | customer instruction |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 13. Order — `orders`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| order_number | VARCHAR(32) | No | Yes | — | human reference |
| customer_id | UUID | No | No | customer_profiles.id | ordering customer |
| branch_id | UUID | No | No | restaurant_branches.id | fulfilment branch |
| delivery_address_id | UUID | Yes | No | addresses.id | source address |
| delivery_address_snapshot | JSON | No | No | — | immutable delivery address |
| status | OrderStatus enum | No | No | — | current required workflow state |
| subtotal, delivery_fee, total_amount | DECIMAL(12,2) | No | No | — | monetary snapshot |
| customer_note | VARCHAR(500) | Yes | No | — | order instruction |
| placed_at | TS | No | No | — | checkout time |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 14. OrderItem — `order_items`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| order_id | UUID | No | No | orders.id | parent order |
| product_variant_id | UUID | Yes | No | product_variants.id | source variant, retained if valid |
| product_name_snapshot | VARCHAR(160) | No | No | — | immutable product name |
| variant_name_snapshot | VARCHAR(120) | Yes | No | — | immutable variant name when selected |
| unit_price | DECIMAL(12,2) | No | No | — | checkout unit price |
| quantity | INTEGER | No | No | — | positive quantity |
| line_total | DECIMAL(12,2) | No | No | — | unit price × quantity |
| notes | VARCHAR(500) | Yes | No | — | preserved instruction |
| created_at | TS | No | No | — | creation audit |

### 15. OrderStatusHistory — `order_status_history`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| order_id | UUID | No | No | orders.id | tracked order |
| from_status, to_status | OrderStatus enum | Yes/No | No | — | transition audit |
| changed_by_user_id | UUID | Yes | No | users.id | actor; null only system event |
| reason | VARCHAR(500) | Yes | No | — | explanatory note |
| created_at | TS | No | No | — | transition time |

## Payments and delivery

### 16. Payment — `payments`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| order_id | UUID | No | No | orders.id | paid order |
| amount | DECIMAL(12,2) | No | No | — | authorized/captured amount |
| currency | CHAR(3) | No | No | — | ISO currency |
| provider | VARCHAR(60) | No | No | — | processor/cash method |
| provider_reference | VARCHAR(150) | Yes | Yes | — | internal simulation reconciliation reference |
| status | PaymentStatus enum | No | No | — | PENDING, AUTHORIZED, CAPTURED, FAILED, REFUNDED |
| paid_at | TS | Yes | No | — | settlement time |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 17. Refund — `refunds`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| payment_id | UUID | No | No | payments.id | refunded payment |
| amount | DECIMAL(12,2) | No | No | — | refunded amount |
| reason | VARCHAR(500) | No | No | — | business explanation |
| provider_reference | VARCHAR(150) | Yes | Yes | — | internal simulation refund reference |
| status | RefundStatus enum | No | No | — | PENDING, SUCCEEDED, FAILED |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 18. Driver — `drivers`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| user_id | UUID | No | Yes | users.id | driver identity (1:1) |
| vehicle_type | VARCHAR(50) | No | No | — | bike/car/etc. |
| vehicle_identifier | VARCHAR(80) | Yes | Yes | — | plate/fleet ID |
| is_available | BOOLEAN | No | No | — | dispatch eligibility |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 19. Delivery — `deliveries`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| order_id | UUID | No | Yes | orders.id | one delivery per order |
| driver_id | UUID | Yes | No | drivers.id | assigned driver |
| status | DeliveryStatus enum | No | No | — | current execution state |
| assigned_at, picked_up_at, delivered_at | TS | Yes | No | — | operational milestones |
| created_at, updated_at | TS | No | No | — | audit timestamps |

### 20. DeliveryStatusHistory — `delivery_status_history`
| Field | Type | Null | Unique | FK | Purpose |
|---|---|---|---|---|---|
| id | UUID | No | Yes | — | primary key |
| delivery_id | UUID | No | No | deliveries.id | tracked delivery |
| from_status, to_status | DeliveryStatus enum | Yes/No | No | — | transition audit |
| changed_by_user_id | UUID | Yes | No | users.id | driver/staff/system actor |
| note | VARCHAR(500) | Yes | No | — | context |
| created_at | TS | No | No | — | transition time |

## Relationships, constraints, and deletion

Final constraint implementation: Partial unique indexes now enforce one plain product per cart and one selected variant per cart; adding the same selection increments quantity. A separate partial unique index enforces one active cart per customer. RestaurantStaff has separate null-safe global and branch-scoped unique indexes, and addresses have a partial unique index for one default per user.

- One-to-one: User–CustomerProfile; User–Driver; Order–Delivery. Enforce unique FKs.
- One-to-many: User–Address, Restaurant–Branch/Menu, Menu–Category, Category–Product, Product–Variant, Cart–CartItem, Order–OrderItem/OrderStatusHistory/Payment, Payment–Refund, Driver–Delivery, Delivery–DeliveryStatusHistory.
- Many-to-many: User–Restaurant through `RestaurantStaff`. Partial unique indexes enforce one global `(restaurant_id, user_id)` membership where `branch_id IS NULL`, and one branch `(restaurant_id, user_id, branch_id)` membership where it is non-null.
- Additional unique constraints: `(restaurant_id, name)` for branches and menus; `(menu_id, name)` for categories; `(product_id, name)` for variants. Partial unique indexes enforce one default address per user, one active cart per customer, and one line per cart/product/optional-variant selection.
- Index design recommendations (not claims of full-text/geospatial implementation): `users(email)`, `addresses(user_id, is_default)`, `restaurants(slug, is_active)` plus name search, `restaurant_branches(restaurant_id, is_active, city)`, `products(category_id, is_available, base_price)` plus full-text/name search, `orders(customer_id, status, placed_at)`, `orders(branch_id, status, placed_at)`, and history/payment/delivery FK indexes.
- Restrict deletion of referenced catalogue, addresses, users, orders, payments, and drivers. Soft-deactivate operational masters instead. Cascade-delete only dependent drafts: Cart → CartItem. History, order items, refunds, and delivery records are retained; they are never cascade-deleted in production.

## State and transaction design

`orders.status` stores the current state. The Stage 6 service accepts only adjacent transitions `PENDING → CONFIRMED → PREPARING → READY_FOR_PICKUP → OUT_FOR_DELIVERY → DELIVERED`, updates the order, and inserts `OrderStatusHistory` in the same transaction. The history captures before/after state, actor, reason, and timestamp; it is append-only.

The delivery design uses `UNASSIGNED → ASSIGNED → PICKED_UP → IN_TRANSIT → DELIVERED`; it records every change in append-only DeliveryStatusHistory. Assignment must occur no earlier than the restaurant-side ready-for-pickup stage, while pickup/in-transit supports the order’s out-for-delivery stage.

Stage 6 checkout is a single database transaction: lock/validate the active cart and variant availability, calculate server-side totals, create Order and OrderItems, add initial status history and PENDING Payment, and clear the cart. Atomicity prevents an order without lines or a cart cleared after a failed payment-record creation. Stage 7 adds explicit ADMIN confirmation/failure of that payment and successful refunds against captured amounts; no external processor is invoked.

## Query readiness

Product search uses parameterized case-insensitive name matching, category FK, Menu → Restaurant joins, base price and availability. Restaurant listing uses name search, active state and branch-city matching (no full-text or geospatial engine). Order listing uses scoped customer/branch FKs, status and placed_at. Primary lists support allowlisted sorting and deterministic ID tie-breakers; see actual query schemas for defaults.


## Final compatibility routes and historical safety

POST /orders aliases checkout. POST /payments idempotently resolves the initial checkout-created payment; it never creates another financial record. POST /deliveries/{delivery_id}/assign-driver aliases existing assignment. Order-referenced addresses cannot be deleted; editing source addresses leaves snapshots unchanged. SQLite foreign keys are enabled on app/test connections. Final migration head: c5b21d4e8f32. See stage10_review.md.
