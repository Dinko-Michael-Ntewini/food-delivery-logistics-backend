# Stage 1 — Requirements and Domain Foundation

> Historical stage snapshot. Earlier test counts, deferred capabilities and scope exclusions describe that stage only. For the final implementation, compatibility routes, constraints and verification results, see [Stage 10 review](stage10_review.md) and [final deliverables](final_deliverables.md).

## Objective

Design the database-ready domain foundation for an original Food Delivery & Logistics Platform. This stage defines requirements, entities, relationships, workflows, and architecture decisions only. It deliberately contains no FastAPI app, SQLAlchemy models, migrations, routes, authentication implementation, or business logic.

## Core domains

| Domain | Responsibility | Required entities |
|---|---|---|
| Identity & customer | login identity, customer data, delivery addresses | User, Address, CustomerProfile |
| Restaurant catalogue | restaurants, branches, staff, menus and sellable items | Restaurant, RestaurantBranch, RestaurantStaff, Menu, Category, Product, ProductVariant |
| Ordering | saved basket, immutable order snapshots, workflow audit | Cart, CartItem, Order, OrderItem, OrderStatusHistory |
| Payments | payment intent/outcome and post-payment reversal | Payment, Refund |
| Delivery | driver capability, delivery execution and audit | Driver, Delivery, DeliveryStatusHistory |

## Required core entities

The model has exactly these 20 business entities: User, Address, CustomerProfile, Restaurant, RestaurantBranch, RestaurantStaff, Menu, Category, Product, ProductVariant, Cart, CartItem, Order, OrderItem, OrderStatusHistory, Payment, Refund, Driver, Delivery, and DeliveryStatusHistory. `restaurant_staff` is also the genuine User–Restaurant association table; it remains one of the required business entities rather than an extra core entity.

## Future technical requirements

The later Python/FastAPI/SQLAlchemy/Pydantic implementation must support authentication, RBAC, search, filtering, pagination, sorting, order state validation, atomic transactions, tests, OpenAPI/Swagger, a Postman collection, and a technical README. This schema reserves the fields, constraints, and indexes needed for those capabilities.

## Main workflows

1. A user registers; a customer creates one customer profile and delivery addresses.
2. A restaurant operates one or more branches; authorized staff manage its catalogue.
3. A customer adds products (optionally with variants) to a cart; the first item explicitly selects a branch. Checkout into an order and payment record is future work.
4. Restaurant staff progress the order through the required state sequence. Each change is recorded with its actor.
5. A driver is assigned after an order is ready for pickup, progresses delivery status, and creates delivery-history records.
6. A payment may later receive one or more partial or full refunds, never exceeding the captured payment amount.

## Constraints and design decisions

- IDs are UUIDs; money uses `DECIMAL(12,2)` and never floating point.
- Passwords are stored only as password hashes. `User.role` is an enum for the initial single-primary-role design.
- A user may have one customer profile only when acting as a customer. A driver profile is likewise one-to-one with a user.
- An empty cart belongs to one customer and may have no branch. Its first item explicitly selects a branch; a non-empty cart is branch-scoped. Removing the final item clears the scope.
- An order stores immutable product-name, optional variant-name, unit-price, and address snapshots. Product or address edits cannot rewrite history. SKU is catalogue metadata, not a separate final OrderItem snapshot field.
- Restaurant membership is a real many-to-many relationship: a user can work at several restaurants and a restaurant can have several users; `RestaurantStaff` stores membership role, branch scope, and employment state.
- `Order.delivery_address_snapshot` is JSON copied from the chosen Address at checkout; the source address is retained as nullable `delivery_address_id` for traceability.
- Required order states are `PENDING → CONFIRMED → PREPARING → READY_FOR_PICKUP → OUT_FOR_DELIVERY → DELIVERED`. Cancellation and failure policies are intentionally deferred rather than added silently.
- Proposed delivery states, owned by this design, are `UNASSIGNED → ASSIGNED → PICKED_UP → IN_TRANSIT → DELIVERED`. They align with, but do not replace, the order workflow.
- Timestamps are UTC and are server-generated in the future implementation.

## Architecture boundary

Stage 1 outputs are documentation and an ER diagram. The next stages may map this design to SQLAlchemy, enforce constraints in migrations, and expose it through FastAPI services and routes.
