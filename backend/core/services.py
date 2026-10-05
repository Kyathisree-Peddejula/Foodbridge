import logging

from django.conf import settings
from django.core.mail import send_mail

from core.models import Notification

log = logging.getLogger(__name__)


def notify(organization, title, body="", kind=Notification.Kind.SYSTEM, link="", data=None, email=True):
    """Create an in-app notification for an organization and email its members."""
    if organization is None:
        return None
    n = Notification.objects.create(organization=organization, title=title, body=body,
                                    kind=kind, link=link, data=data or {})
    if email:
        recipients = [u.email for u in organization.members.filter(is_active=True) if u.email]
        if organization.contact_email:
            recipients.append(organization.contact_email)
        if recipients:
            try:
                send_mail(f"[FoodBridge] {title}", body or title, settings.DEFAULT_FROM_EMAIL,
                          sorted(set(recipients)), fail_silently=True)
            except Exception:  # never block the request on email
                log.exception("email failed")
    return n
