import smtplib
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from core.config import settings

class EmailSettings:
    SMTP_HOST = settings.smtp_host
    SMTP_PORT = int(settings.smtp_port)
    SMTP_USERNAME = settings.smtp_username
    SMTP_PASSWORD = settings.smtp_password
    FROM_EMAIL = settings.from_email
    FROM_NAME = settings.from_name

class EmailService:
    @staticmethod
    def _render_template(template_name: str, **template_vars) -> str:
        templates_dir = Path(__file__).resolve().parent.parent / "templates"
        template_path = templates_dir / template_name

        if not template_path.exists():
            raise Exception(f"Email template not found: {template_path}")

        template = template_path.read_text(encoding="utf-8")

        try:
            return template.format(**template_vars)
        except KeyError as e:
            raise Exception(f"Missing template variable in {template_name}: {str(e)}")

    @staticmethod
    def _build_verification_email_html(name: str, code: str, expiry_minutes: int) -> str:
        return EmailService._render_template(
            "verification.html",
            name=name,
            code=code,
            expiry_minutes=expiry_minutes,
        )

    @staticmethod
    def _build_forgot_password_email_html(name: str, code: str, expiry_minutes: int) -> str:
        return EmailService._render_template(
            "forgot-password.html",
            name=name,
            code=code,
            expiry_minutes=expiry_minutes,
        )

    @staticmethod
    def _build_password_reset_success_email_html(name: str) -> str:
        return EmailService._render_template(
            "password-reset-success.html",
            name=name,
        )

    @staticmethod
    def send_verification_email(to_email: str, name: str, code: str, expiry_minutes: int = 15) -> None:
        if not EmailSettings.SMTP_USERNAME or not EmailSettings.SMTP_PASSWORD:
            raise Exception("SMTP credentials are missing. Set SMTP_USERNAME and SMTP_PASSWORD.")

        subject = "Mali verification code"
        html_body = EmailService._build_verification_email_html(
            name=name,
            code=code,
            expiry_minutes=expiry_minutes,
        )
        text_body = (
            f"Hi {name},\n\n"
            f"Your Mali verification code is: {code}\n"
            f"This code expires in {expiry_minutes} minutes.\n\n"
            f"If you did not request this, ignore this email."
        )

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{EmailSettings.FROM_NAME} <{EmailSettings.FROM_EMAIL}>"
        message["To"] = to_email
        message.attach(MIMEText(text_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL(EmailSettings.SMTP_HOST, EmailSettings.SMTP_PORT) as server:
            server.login(EmailSettings.SMTP_USERNAME, EmailSettings.SMTP_PASSWORD)
            server.sendmail(EmailSettings.FROM_EMAIL, [to_email], message.as_string())

    @staticmethod
    def send_forgot_password_email(to_email: str, name: str, code: str, expiry_minutes: int = 15) -> None:
        if not EmailSettings.SMTP_USERNAME or not EmailSettings.SMTP_PASSWORD:
            raise Exception("SMTP credentials are missing. Set SMTP_USERNAME and SMTP_PASSWORD.")

        subject = "Mali password reset code"
        html_body = EmailService._build_forgot_password_email_html(
            name=name,
            code=code,
            expiry_minutes=expiry_minutes,
        )
        text_body = (
            f"Hi {name},\n\n"
            f"Your Mali password reset code is: {code}\n"
            f"This code expires in {expiry_minutes} minutes.\n\n"
            f"If you did not request this, ignore this email."
        )

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{EmailSettings.FROM_NAME} <{EmailSettings.FROM_EMAIL}>"
        message["To"] = to_email
        message.attach(MIMEText(text_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL(EmailSettings.SMTP_HOST, EmailSettings.SMTP_PORT) as server:
            server.login(EmailSettings.SMTP_USERNAME, EmailSettings.SMTP_PASSWORD)
            server.sendmail(EmailSettings.FROM_EMAIL, [to_email], message.as_string())

    @staticmethod
    def send_password_reset_success_email(to_email: str, name: str) -> None:
        if not EmailSettings.SMTP_USERNAME or not EmailSettings.SMTP_PASSWORD:
            raise Exception("SMTP credentials are missing. Set SMTP_USERNAME and SMTP_PASSWORD.")

        subject = "Mali password reset successful"
        html_body = EmailService._build_password_reset_success_email_html(name=name)
        text_body = (
            f"Hi {name},\n\n"
            "Your Mali password was reset successfully.\n\n"
            "If you did not perform this password reset, contact support immediately to secure your account."
        )

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{EmailSettings.FROM_NAME} <{EmailSettings.FROM_EMAIL}>"
        message["To"] = to_email
        message.attach(MIMEText(text_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL(EmailSettings.SMTP_HOST, EmailSettings.SMTP_PORT) as server:
            server.login(EmailSettings.SMTP_USERNAME, EmailSettings.SMTP_PASSWORD)
            server.sendmail(EmailSettings.FROM_EMAIL, [to_email], message.as_string())