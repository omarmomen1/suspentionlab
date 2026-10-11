"""
Legacy re-export for backward compatibility.
Provider logic moved to gumroad_routes.py.
"""
from suspensionlab.backend.api.routes.gumroad_routes import router, LicenseVerificationRequest, LicenseVerificationResponse, verify_gumroad_license

__all__ = ["router", "LicenseVerificationRequest", "LicenseVerificationResponse", "verify_gumroad_license"]
