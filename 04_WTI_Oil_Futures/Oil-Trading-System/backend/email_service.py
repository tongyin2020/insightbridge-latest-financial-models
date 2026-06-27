"""
WTI Trading Platform - Email Service with SendGrid
Handles user verification and notification emails
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
import secrets

logger = logging.getLogger(__name__)

# Try to import sendgrid, fallback to logging if not available
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.warning("[Email] SendGrid not installed, emails will be logged only")


class EmailService:
    """Service for sending emails via SendGrid"""
    
    def __init__(self):
        self.api_key = os.environ.get("SENDGRID_API_KEY")
        self.sender_email = os.environ.get("SENDER_EMAIL", "noreply@wti-trading.com")
        self.frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        self._enabled = bool(self.api_key and SENDGRID_AVAILABLE)
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    async def send_email(
        self, 
        to_email: str, 
        subject: str, 
        html_content: str,
        plain_content: Optional[str] = None
    ) -> bool:
        """Send an email via SendGrid"""
        
        if not self._enabled:
            logger.info(f"[Email] Would send to {to_email}: {subject}")
            logger.debug(f"[Email] Content: {html_content[:200]}...")
            return True
        
        try:
            message = Mail(
                from_email=Email(self.sender_email),
                to_emails=To(to_email),
                subject=subject,
                html_content=Content("text/html", html_content)
            )
            
            if plain_content:
                message.add_content(Content("text/plain", plain_content))
            
            sg = SendGridAPIClient(self.api_key)
            response = sg.send(message)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"[Email] Sent to {to_email}: {subject}")
                return True
            else:
                logger.error(f"[Email] Failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[Email] Error sending email: {e}")
            return False
    
    async def send_verification_email(self, to_email: str, token: str, user_name: str) -> bool:
        """Send email verification link"""
        
        verification_url = f"{self.frontend_url}/verify-email?token={token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #09090B; color: #ffffff; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #18181B; border-radius: 8px; padding: 40px; border: 1px solid #27272A; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .logo {{ font-size: 24px; font-weight: bold; color: #3B82F6; }}
                .content {{ line-height: 1.6; color: #A1A1AA; }}
                .button {{ display: inline-block; background: #3B82F6; color: white; padding: 12px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
                .button:hover {{ background: #2563EB; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #52525B; text-align: center; }}
                .code {{ background: #27272A; padding: 15px; border-radius: 4px; font-family: monospace; margin: 15px 0; word-break: break-all; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">⚡ Energy AI Trading</div>
                </div>
                <div class="content">
                    <h2 style="color: #ffffff;">Verify Your Email</h2>
                    <p>Hi {user_name},</p>
                    <p>Thank you for registering with Energy AI Trading Platform. Please verify your email address by clicking the button below:</p>
                    <div style="text-align: center;">
                        <a href="{verification_url}" class="button">Verify Email</a>
                    </div>
                    <p>Or copy and paste this link in your browser:</p>
                    <div class="code">{verification_url}</div>
                    <p>This link will expire in 24 hours.</p>
                    <p>If you didn't create an account, you can safely ignore this email.</p>
                </div>
                <div class="footer">
                    <p>© 2026 Energy AI Trading Platform. All rights reserved.</p>
                    <p>This is an automated message, please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_content = f"""
        Verify Your Email
        
        Hi {user_name},
        
        Thank you for registering with Energy AI Trading Platform. 
        Please verify your email address by visiting:
        
        {verification_url}
        
        This link will expire in 24 hours.
        
        If you didn't create an account, you can safely ignore this email.
        """
        
        return await self.send_email(
            to_email=to_email,
            subject="Verify your Energy AI Trading account",
            html_content=html_content,
            plain_content=plain_content
        )
    
    async def send_password_reset_email(self, to_email: str, token: str, user_name: str) -> bool:
        """Send password reset link"""
        
        reset_url = f"{self.frontend_url}/reset-password?token={token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #09090B; color: #ffffff; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #18181B; border-radius: 8px; padding: 40px; border: 1px solid #27272A; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .logo {{ font-size: 24px; font-weight: bold; color: #3B82F6; }}
                .content {{ line-height: 1.6; color: #A1A1AA; }}
                .button {{ display: inline-block; background: #EF4444; color: white; padding: 12px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
                .warning {{ background: #7F1D1D; border: 1px solid #DC2626; padding: 15px; border-radius: 4px; margin: 15px 0; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #52525B; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">⚡ Energy AI Trading</div>
                </div>
                <div class="content">
                    <h2 style="color: #ffffff;">Password Reset Request</h2>
                    <p>Hi {user_name},</p>
                    <p>We received a request to reset your password. Click the button below to set a new password:</p>
                    <div style="text-align: center;">
                        <a href="{reset_url}" class="button">Reset Password</a>
                    </div>
                    <div class="warning">
                        <strong>⚠️ Security Notice:</strong> This link will expire in 1 hour. If you didn't request this, please ignore this email and your password will remain unchanged.
                    </div>
                </div>
                <div class="footer">
                    <p>© 2026 Energy AI Trading Platform. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(
            to_email=to_email,
            subject="Reset your Energy AI Trading password",
            html_content=html_content
        )
    
    async def send_trade_alert(
        self, 
        to_email: str, 
        user_name: str,
        trade_type: str,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: int,
        pnl: Optional[float] = None
    ) -> bool:
        """Send trade execution alert"""
        
        if trade_type == "open":
            subject = f"🔔 Position Opened: {direction.upper()} {symbol}"
            action_text = f"Opened {direction.upper()} position"
            pnl_section = ""
        else:
            subject = f"📊 Position Closed: {symbol}"
            action_text = f"Closed {direction.upper()} position"
            pnl_color = "#10B981" if pnl and pnl >= 0 else "#EF4444"
            pnl_sign = "+" if pnl and pnl >= 0 else ""
            pnl_section = f'<p style="font-size: 24px; color: {pnl_color}; font-weight: bold;">P&L: {pnl_sign}${pnl:.2f}</p>'
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #09090B; color: #ffffff; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #18181B; border-radius: 8px; padding: 40px; border: 1px solid #27272A; }}
                .trade-info {{ background: #27272A; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .trade-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
                .label {{ color: #71717A; }}
                .value {{ color: #ffffff; font-weight: 600; font-family: monospace; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>{action_text}</h2>
                <div class="trade-info">
                    <div class="trade-row">
                        <span class="label">Symbol:</span>
                        <span class="value">{symbol}</span>
                    </div>
                    <div class="trade-row">
                        <span class="label">Direction:</span>
                        <span class="value" style="color: {'#10B981' if direction == 'long' else '#EF4444'};">{direction.upper()}</span>
                    </div>
                    <div class="trade-row">
                        <span class="label">Price:</span>
                        <span class="value">${entry_price:.2f}</span>
                    </div>
                    <div class="trade-row">
                        <span class="label">Quantity:</span>
                        <span class="value">{quantity}</span>
                    </div>
                </div>
                {pnl_section}
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content
        )
    
    async def send_risk_alert(
        self, 
        to_email: str, 
        user_name: str,
        alert_type: str,
        message: str
    ) -> bool:
        """Send risk management alert"""
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #09090B; color: #ffffff; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #18181B; border-radius: 8px; padding: 40px; border: 1px solid #7F1D1D; }}
                .alert {{ background: #7F1D1D; padding: 20px; border-radius: 8px; text-align: center; }}
                .alert-icon {{ font-size: 48px; margin-bottom: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="alert">
                    <div class="alert-icon">⚠️</div>
                    <h2 style="margin: 0; color: #FCA5A5;">RISK ALERT: {alert_type.upper()}</h2>
                </div>
                <p style="margin-top: 20px; color: #A1A1AA;">{message}</p>
                <p style="color: #71717A; font-size: 12px;">
                    This is an automated risk management alert. Please review your positions immediately.
                </p>
            </div>
        </body>
        </html>
        """
        
        return await self.send_email(
            to_email=to_email,
            subject=f"🚨 Risk Alert: {alert_type}",
            html_content=html_content
        )


def generate_verification_token() -> str:
    """Generate a secure verification token"""
    return secrets.token_urlsafe(32)
