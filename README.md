# Shop Project

Online shop REST API built with Django and Django REST Framework.

## Features
- JWT authentication (sign up, sign in, token refresh) and user profile
- Catalog: categories, base products, products with colors, warranties, options and features
- Search and filtering for products
- Basket and orders (checkout / cancel)
- Zarinpal (sandbox) payment request and verification
- Swagger / ReDoc API documentation

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data      # optional demo data
python manage.py runserver
```

## Endpoints
| Path | Description |
|------|-------------|
| `/admin/` | Django admin |
| `/api/auth/signup/`, `/api/auth/signin/`, `/api/auth/token/refresh/` | Authentication |
| `/api/profile/` | Current user profile |
| `/api/categories/`, `/api/base-products/`, `/api/products/` | Catalog |
| `/api/basket/`, `/api/orders/` | Basket and orders |
| `/api/payments/verify/` | Zarinpal payment verification |
| `/api/docs/`, `/api/redoc/` | API documentation |

## Git flow
`main` holds releases, `develop` is the integration branch, work happens in `feature/*`, releases are cut from `release/*`.
