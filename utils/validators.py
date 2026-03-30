"""
Custom validators for DealSphere
"""

import re
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from decimal import Decimal

def validate_phone_number(value):
    """Validate phone number"""
    if not value:
        return  # Optional field
    
    # Remove spaces, dashes, parentheses
    phone = re.sub(r'[\s\-\(\)]', '', value)
    
    # Check if it's a valid Indian phone number
    if not re.match(r'^[6-9]\d{9}$', phone):
        raise ValidationError('Please enter a valid 10-digit Indian mobile number')
    
    return phone


def validate_strong_password(value):
    """Validate password strength required by the frontend workflow."""
    password = str(value or "")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must include at least one uppercase letter.")
    if not re.search(r"\d", password):
        raise ValidationError("Password must include at least one number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValidationError("Password must include at least one special character.")
    return password

def validate_gstin(value):
    """Validate GSTIN number"""
    if not value:
        return  # Optional field
    
    # GSTIN format: 2 digits state code + 10 digits PAN + 1 digit entity number + 1 check digit + Z
    gstin_pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9Z][A-Z0-9]$'
    
    if not re.match(gstin_pattern, value.upper()):
        raise ValidationError('Please enter a valid GSTIN number')
    
    return value.upper()

def validate_price(value):
    """Validate price"""
    try:
        price = Decimal(str(value))
    except (ValueError, TypeError):
        raise ValidationError('Invalid price format')
    
    if price <= 0:
        raise ValidationError('Price must be greater than 0')
    
    if price > Decimal('99999999.99'):
        raise ValidationError('Price cannot exceed 9,99,99,999.99')
    
    return price

def validate_location(lat, lng):
    """Validate latitude and longitude"""
    if lat is not None and lng is not None:
        try:
            latitude = float(lat)
            longitude = float(lng)
            
            if not (-90 <= latitude <= 90):
                raise ValidationError('Latitude must be between -90 and 90')
            
            if not (-180 <= longitude <= 180):
                raise ValidationError('Longitude must be between -180 and 180')
                
        except (ValueError, TypeError):
            raise ValidationError('Invalid latitude or longitude format')

def validate_barcode(value):
    """Validate barcode"""
    if not value:
        return  # Optional field
    
    # Remove spaces
    barcode = value.replace(' ', '')
    
    # Check if it contains only digits
    if not barcode.isdigit():
        raise ValidationError('Barcode must contain only digits')
    
    # Check length (8, 12, 13, or 14 digits are common)
    if len(barcode) not in [8, 12, 13, 14]:
        raise ValidationError('Barcode must be 8, 12, 13, or 14 digits long')
    
    return barcode

def validate_delivery_time(value):
    """Validate delivery time in hours"""
    try:
        hours = int(value)
    except (ValueError, TypeError):
        raise ValidationError('Delivery time must be a whole number of hours')
    
    if hours < 1:
        raise ValidationError('Delivery time must be at least 1 hour')
    
    if hours > 168:  # 1 week
        raise ValidationError('Delivery time cannot exceed 168 hours (1 week)')
    
    return hours

def validate_discount_percentage(value):
    """Validate discount percentage"""
    try:
        percentage = float(value)
    except (ValueError, TypeError):
        raise ValidationError('Discount percentage must be a number')
    
    if percentage < 0:
        raise ValidationError('Discount percentage cannot be negative')
    
    if percentage > 100:
        raise ValidationError('Discount percentage cannot exceed 100')
    
    return percentage

def validate_stock_quantity(value):
    """Validate stock quantity"""
    try:
        quantity = int(value)
    except (ValueError, TypeError):
        raise ValidationError('Stock quantity must be a whole number')
    
    if quantity < 0:
        raise ValidationError('Stock quantity cannot be negative')
    
    if quantity > 10000:
        raise ValidationError('Stock quantity cannot exceed 10,000')
    
    return quantity

def validate_pincode(value):
    """Validate Indian PIN code"""
    if not value:
        return  # Optional field
    
    if not re.match(r'^[1-9][0-9]{5}$', value):
        raise ValidationError('Please enter a valid 6-digit Indian PIN code')
    
    return value

# Custom regex validators
phone_validator = RegexValidator(
    regex=r'^[6-9]\d{9}$',
    message='Phone number must be a valid 10-digit Indian mobile number starting with 6-9'
)

gstin_validator = RegexValidator(
    regex=r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9Z][A-Z0-9]$',
    message='GSTIN must be in the format: 2 digits + 5 letters + 4 digits + 1 letter + 1 digit/letter + Z'
)

barcode_validator = RegexValidator(
    regex=r'^[0-9]{8,14}$',
    message='Barcode must be 8-14 digits long'
)

pincode_validator = RegexValidator(
    regex=r'^[1-9][0-9]{5}$',
    message='PIN code must be a valid 6-digit Indian PIN code'
)
