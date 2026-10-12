from __future__ import annotations

from config import AgentSettings


class PaymentManager:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings

    def ask_for_payment_preferences(self) -> str:
        if not self.settings.default_payment_method or not self.settings.payment_schedule:
            return (
                "I can help you organize your payment schedule. "
                "Please tell me when you want to be paid and which method you prefer, like bank transfer, PayPal, or UPI."
            )
        return (
            f"Your payment plan is set to {self.settings.payment_schedule} and {self.settings.default_payment_method}. "
            "If you want, I can help you plan your earnings and reminders."
        )

    def update_preferences(self, payment_schedule: str, method: str) -> str:
        self.settings.payment_schedule = payment_schedule.strip() or self.settings.payment_schedule
        self.settings.default_payment_method = method.strip() or self.settings.default_payment_method
        self.settings.save()
        return (
            f"Thanks. I saved your payment plan as {self.settings.payment_schedule} and the payment method as {self.settings.default_payment_method}."
        )

    def parse_payment_request(self, text: str) -> str:
        lower = text.lower()
        schedule = "daily"
        method = self.settings.default_payment_method

        if any(word in lower for word in ["weekly", "week"]):
            schedule = "weekly"
        elif any(word in lower for word in ["monthly", "month"]):
            schedule = "monthly"

        if any(word in lower for word in ["bank transfer", "bank", "wire"]):
            method = "Bank transfer"
        elif any(word in lower for word in ["paypal", "pay pal"]):
            method = "PayPal"
        elif any(word in lower for word in ["upi", "phonepe", "google pay", "paytm"]):
            method = "UPI"
        elif any(word in lower for word in ["cash", "manual"]):
            method = "Cash"

        return self.update_preferences(schedule, method)

    def guidance(self) -> str:
        return (
            "I can help you manage your earnings. Please tell me: 1) when you want to be paid, "
            "for example daily, weekly, or monthly, and 2) how you want to receive it, such as bank transfer, PayPal, or UPI."
        )
