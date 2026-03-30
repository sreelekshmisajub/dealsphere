import re
from django import template

register = template.Library()


@register.filter
def pretty_category(value):
    """
    Turn raw DB category names into readable display names.
    e.g. 'Home&Kitchen' → 'Home & Kitchen'
         'HomeImprovement' → 'Home Improvement'
         'Health&PersonalCare' → 'Health & Personal Care'
    """
    s = str(value or "")
    # Insert space before & and after it
    s = s.replace("&", " & ")
    # Insert space before each uppercase letter that follows a lowercase letter
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    # Collapse multiple spaces
    s = re.sub(r" {2,}", " ", s)
    return s.strip()
