#!/usr/bin/env python3
"""Send a rendered test email for the testimonials initiative to mark@bizkite.net."""

import logging
import sys
from pathlib import Path

from cocli.application.email_service import EmailService
from cocli.application.personalized_outreach_service import PersonalizedOutreachService
from cocli.core.config import load_campaign_config
from cocli.models.mail import EmailSettings, SendMailRequest
from cocli.utils.html_to_text import html_to_text

# Configure logging
log_dir = Path(".logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "send_test_testimonial_email.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("send_test_testimonial_email")


def main() -> None:
    campaign_name = "roadmap"
    recipient = "mark@bizkite.net"
    template_id = "request_testimonial.md"
    initiative = "testimonials"

    logger.info("Initializing services for campaign '%s'", campaign_name)
    raw = load_campaign_config(campaign_name) or {}
    email_raw = raw.get("email") or {}
    settings = EmailSettings.model_validate(email_raw)
    aws = raw.get("aws") or {}
    profile = aws.get("profile")

    outreach_service = PersonalizedOutreachService(campaign_name)
    email_service = EmailService(campaign_name, settings, aws_profile=profile)

    subject_pattern, body_template = outreach_service.load_template(template_id, initiative=initiative)
    layout = outreach_service._layout_for_template(template_id, initiative=initiative)

    subject = "[TEST] Mark, are you having any problems with Retirement Tax Analyzer?"
    # Personalize markdown body
    body_md = body_template.replace("{first_name}", "Mark")
    # Replace any relative or template links with proper test UTM
    body_md = body_md.replace("{company_slug}", "test")

    if layout:
        html_body = outreach_service.render_markdown_email(body_md, layout, initiative=initiative)
        plain_body = html_to_text(html_body)
    else:
        html_body = None
        plain_body = body_md

    logger.info("Sending test email to %s via backend=%s...", recipient, settings.backend)
    request = SendMailRequest(
        to_address=recipient,
        subject=subject,
        body=plain_body,
        html_body=html_body,
        company_slug="ses-roundtrip-test",
    )

    result = email_service.send(request)
    logger.info("Successfully sent test email!")
    logger.info("Message ID: %s", result.message_id)
    logger.info("Recipient: %s", result.to_address)
    logger.info("Company note written: %s (slug: %s)", result.note_written, result.company_slug)


if __name__ == "__main__":
    main()
