"""Small client for the Zarinpal REST v4 gateway (sandbox or production)."""
import requests
from django.conf import settings


class ZarinpalError(Exception):
    pass


def _host():
    if settings.ZARINPAL_SANDBOX:
        return "https://sandbox.zarinpal.com"
    return "https://payment.zarinpal.com"


def _post(path, payload):
    try:
        response = requests.post(
            f"{_host()}/pg/v4/payment/{path}",
            json=payload,
            headers={"Accept": "application/json"},
            timeout=15,
        )
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ZarinpalError("Could not connect to the payment gateway.") from exc


def _error_message(body):
    errors = body.get("errors")
    if isinstance(errors, dict) and errors.get("message"):
        return f"{errors.get('message')} (code {errors.get('code')})"
    return "Unexpected response from the payment gateway."


def request_payment(amount_rial, description, callback_url):
    """Start a payment and return its authority code."""
    body = _post(
        "request.json",
        {
            "merchant_id": settings.ZARINPAL_MERCHANT_ID,
            "amount": amount_rial,
            "description": description,
            "callback_url": callback_url,
        },
    )
    data = body.get("data")
    if isinstance(data, dict) and data.get("code") == 100 and data.get("authority"):
        return data["authority"]
    raise ZarinpalError(_error_message(body))


def start_pay_url(authority):
    return f"{_host()}/pg/StartPay/{authority}"


def verify_payment(amount_rial, authority):
    """Return the bank ref_id if the payment is verified, otherwise raise."""
    body = _post(
        "verify.json",
        {
            "merchant_id": settings.ZARINPAL_MERCHANT_ID,
            "amount": amount_rial,
            "authority": authority,
        },
    )
    data = body.get("data")
    # 100 = verified now, 101 = already verified before
    if isinstance(data, dict) and data.get("code") in (100, 101):
        return str(data.get("ref_id", ""))
    raise ZarinpalError(_error_message(body))
