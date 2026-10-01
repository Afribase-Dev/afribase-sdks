"""AfribaseEmailClient — send transactional emails from your app."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from afribase._http import handle_response, sync_request


class AfribaseEmailClient:
    """Send transactional emails using your project's configured SMTP provider.

    Access via ``client.email``.

    Usage::

        # Using a saved custom template
        result = client.email.send(
            to="user@example.com",
            template_id="welcome",
            template_vars={"name": "John", "plan": "Pro"},
        )

        # Raw send (no template required)
        result = client.email.send(
            to="user@example.com",
            subject="Hello from MyApp",
            html="<h1>Hello John!</h1>",
        )

        # List saved templates
        templates = client.email.list_templates()
    """

    def __init__(self, *, url: str, slug: str, api_key: str, get_access_token: Any) -> None:
        self._url = url.rstrip("/")
        self._slug = slug
        self._api_key = api_key
        self._get_token = get_access_token

    def send(
        self,
        *,
        to: str,
        template_id: Optional[str] = None,
        template_vars: Optional[Dict[str, str]] = None,
        subject: Optional[str] = None,
        html: Optional[str] = None,
        from_: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a transactional email.

        Args:
            to: Recipient email address.
            template_id: ID of a saved custom template (created in the dashboard).
            template_vars: Variables substituted as ``{{ .Key }}`` in the template.
            subject: Email subject — required when *template_id* is not provided.
            html: HTML body — required when *template_id* is not provided.
            from_: Override the from address (defaults to SMTP admin email).
            from_name: Override the sender display name.

        Returns:
            Dict with ``"data"`` (``{"status": "sent"}``) and ``"error"`` keys.
        """
        body: Dict[str, Any] = {"to": to}
        if template_id is not None:
            body["template_id"] = template_id
        if template_vars is not None:
            body["template_vars"] = template_vars
        if subject is not None:
            body["subject"] = subject
        if html is not None:
            body["html"] = html
        if from_ is not None:
            body["from"] = from_
        if from_name is not None:
            body["from_name"] = from_name

        resp = sync_request(
            f"{self._url}/{self._slug}/send",
            method="POST",
            api_key=self._api_key,
            access_token=self._get_token(),
            json=body,
        )
        return handle_response(resp)

    def list_templates(self) -> Dict[str, Any]:
        """Return all custom email templates saved for this project.

        Returns:
            Dict with ``"data"`` (list of template dicts) and ``"error"`` keys.
        """
        resp = sync_request(
            f"{self._url}/{self._slug}/templates",
            method="GET",
            api_key=self._api_key,
            access_token=self._get_token(),
        )
        return handle_response(resp)
