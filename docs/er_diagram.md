# Entity Relationship Diagram

Final schema nullability: an empty `CART` may have no branch, and `CART_ITEM.product_variant_id` is optional while `product_id` is required. The first item explicitly selects the branch.

The diagram represents exactly the 20 required business entities. `RESTAURANT_STAFF` is the required membership entity that implements the meaningful User–Restaurant many-to-many relationship.

```mermaid
erDiagram
    USER ||--o| CUSTOMER_PROFILE : has
    USER ||--o{ ADDRESS : owns
    USER ||--o{ RESTAURANT_STAFF : holds
    RESTAURANT ||--o{ RESTAURANT_STAFF : employs
    RESTAURANT ||--o{ RESTAURANT_BRANCH : operates
    RESTAURANT ||--o{ MENU : publishes
    RESTAURANT_BRANCH o|--o{ RESTAURANT_STAFF : scopes
    MENU ||--o{ CATEGORY : groups
    CATEGORY ||--o{ PRODUCT : contains
    PRODUCT ||--o{ PRODUCT_VARIANT : offers
    CUSTOMER_PROFILE ||--o{ CART : owns
    RESTAURANT_BRANCH o|--o{ CART : fulfills
    CART ||--o{ CART_ITEM : contains
    PRODUCT ||--o{ CART_ITEM : selected_as
    PRODUCT_VARIANT o|--o{ CART_ITEM : selected_as
    CUSTOMER_PROFILE ||--o{ ORDER : places
    RESTAURANT_BRANCH ||--o{ ORDER : fulfills
    ADDRESS o|--o{ ORDER : sourced_for
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT_VARIANT o|--o{ ORDER_ITEM : source_of
    ORDER ||--o{ ORDER_STATUS_HISTORY : records
    USER o|--o{ ORDER_STATUS_HISTORY : changes
    ORDER ||--o{ PAYMENT : has
    PAYMENT ||--o{ REFUND : has
    USER ||--o| DRIVER : is
    ORDER ||--o| DELIVERY : ships_as
    DRIVER o|--o{ DELIVERY : performs
    DELIVERY ||--o{ DELIVERY_STATUS_HISTORY : records
    USER o|--o{ DELIVERY_STATUS_HISTORY : changes

    USER {
        UUID id PK
        string email UK
        UserRole role
        boolean is_active
    }
    CUSTOMER_PROFILE {
        UUID id PK
        UUID user_id FK,UK
    }
    ADDRESS {
        UUID id PK
        UUID user_id FK
        string city
        boolean is_default
    }
    RESTAURANT {
        UUID id PK
        string slug UK
        boolean is_active
    }
    RESTAURANT_BRANCH {
        UUID id PK
        UUID restaurant_id FK
        string city
        boolean is_active
    }
    RESTAURANT_STAFF {
        UUID id PK
        UUID restaurant_id FK
        UUID user_id FK
        UUID branch_id FK
    }
    MENU {
        UUID id PK
        UUID restaurant_id FK
        boolean is_active
    }
    CATEGORY {
        UUID id PK
        UUID menu_id FK
        int display_order
    }
    PRODUCT {
        UUID id PK
        UUID category_id FK
        decimal base_price
        boolean is_available
    }
    PRODUCT_VARIANT {
        UUID id PK
        UUID product_id FK
        string sku UK
        decimal price_override
    }
    CART {
        UUID id PK
        UUID customer_id FK
        UUID branch_id FK
        CartStatus status
    }
    CART_ITEM {
        UUID id PK
        UUID cart_id FK
        UUID product_id FK
        UUID product_variant_id FK
        int quantity
    }
    ORDER {
        UUID id PK
        string order_number UK
        UUID customer_id FK
        UUID branch_id FK
        OrderStatus status
        decimal total_amount
    }
    ORDER_ITEM {
        UUID id PK
        UUID order_id FK
        UUID product_variant_id FK
        decimal unit_price
        int quantity
    }
    ORDER_STATUS_HISTORY {
        UUID id PK
        UUID order_id FK
        UUID changed_by_user_id FK
        OrderStatus to_status
    }
    PAYMENT {
        UUID id PK
        UUID order_id FK
        PaymentStatus status
        decimal amount
    }
    REFUND {
        UUID id PK
        UUID payment_id FK
        RefundStatus status
        decimal amount
    }
    DRIVER {
        UUID id PK
        UUID user_id FK,UK
        boolean is_available
    }
    DELIVERY {
        UUID id PK
        UUID order_id FK,UK
        UUID driver_id FK
        DeliveryStatus status
    }
    DELIVERY_STATUS_HISTORY {
        UUID id PK
        UUID delivery_id FK
        UUID changed_by_user_id FK
        DeliveryStatus to_status
    }
```

`CART.branch_id` may be null while empty; `CART_ITEM.product_variant_id` is optional, while `product_id` is required. `ORDER_ITEM.product_variant_id` is nullable to preserve historical orders if a catalogue variant is retired. See [data_model.md](data_model.md) for full nullability.
