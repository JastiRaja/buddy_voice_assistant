import re
from typing import Optional, Tuple

# Baseline Cached Exchange Rates (relative to 1 USD) for Air-Gapped Offline Execution
CURRENCY_RATES = {
    "usd": 1.0,
    "dollar": 1.0,
    "dollars": 1.0,
    "eur": 0.92,
    "euro": 0.92,
    "euros": 0.92,
    "gbp": 0.79,
    "pound": 0.79,
    "pounds": 0.79,
    "inr": 84.0,
    "rupee": 84.0,
    "rupees": 84.0,
    "jpy": 152.0,
    "yen": 152.0,
    "cad": 1.38,
    "aud": 1.52,
    "cny": 7.23,
    "yuan": 7.23
}

LENGTH_UNITS = {
    "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0,
    "m": 1.0, "meter": 1.0, "meters": 1.0,
    "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01,
    "mm": 0.001, "millimeter": 0.001, "millimeters": 0.001,
    "mile": 1609.344, "miles": 1609.344,
    "yard": 0.9144, "yards": 0.9144,
    "foot": 0.3048, "feet": 0.3048, "ft": 0.3048,
    "inch": 0.0254, "inches": 0.0254, "in": 0.0254
}

MASS_UNITS = {
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0, "kilo": 1000.0, "kilos": 1000.0,
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "mg": 0.001, "milligram": 0.001, "milligrams": 0.001,
    "lb": 453.59237, "lbs": 453.59237, "pound": 453.59237, "pounds": 453.59237,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "ton": 1000000.0, "tons": 1000000.0
}

DATA_UNITS = {
    "b": 1.0, "byte": 1.0, "bytes": 1.0,
    "kb": 1024.0, "kilobyte": 1024.0, "kilobytes": 1024.0,
    "mb": 1024.0**2, "megabyte": 1024.0**2, "megabytes": 1024.0**2,
    "gb": 1024.0**3, "gigabyte": 1024.0**3, "gigabytes": 1024.0**3,
    "tb": 1024.0**4, "terabyte": 1024.0**4, "terabytes": 1024.0**4
}


class UnitConverter:
    """Offline unit and currency converter running 100% locally."""

    @staticmethod
    def parse_and_convert(query: str) -> Optional[str]:
        cmd = query.lower().strip()
        cmd = re.sub(r'^(convert|calculate|how many|what is)\s+', '', cmd).strip()

        # 1. Temperature Conversion (e.g. "72 fahrenheit in celsius", "30 c to f")
        temp_match = re.search(r'([\d\.\-]+)\s*(?:degrees?\s+)?(celsius|fahrenheit|kelvin|c|f|k)\s+(?:in|to|into)\s+(?:degrees?\s+)?(celsius|fahrenheit|kelvin|c|f|k)', cmd)
        if temp_match:
            val = float(temp_match.group(1))
            from_unit = temp_match.group(2)
            to_unit = temp_match.group(3)

            # Normalize to Celsius
            if from_unit in ["fahrenheit", "f"]:
                c_val = (val - 32.0) * (5.0 / 9.0)
            elif from_unit in ["kelvin", "k"]:
                c_val = val - 273.15
            else:
                c_val = val

            # Convert to target
            if to_unit in ["fahrenheit", "f"]:
                res = (c_val * 9.0 / 5.0) + 32.0
                unit_str = "degrees Fahrenheit"
            elif to_unit in ["kelvin", "k"]:
                res = c_val + 273.15
                unit_str = "Kelvin"
            else:
                res = c_val
                unit_str = "degrees Celsius"

            return f"{val} in {to_unit} is approximately {round(res, 2)} {unit_str}, sir."

        # 2. General Unit / Currency Conversion: e.g. "15 kilometers to miles", "100 dollars in rupees"
        pattern = r'([\d\.]+)\s*([a-zA-Z\s]+?)\s+(?:in|to|into)\s+([a-zA-Z\s]+)$'
        match = re.search(pattern, cmd)
        if not match:
            return None

        amount = float(match.group(1))
        unit_a = match.group(2).strip().lower()
        unit_b = match.group(3).strip().lower()

        # Currency Check
        if unit_a in CURRENCY_RATES and unit_b in CURRENCY_RATES:
            usd_base = amount / CURRENCY_RATES[unit_a]
            target_amount = usd_base * CURRENCY_RATES[unit_b]
            return f"{amount:,.2f} {unit_a.title()} is approximately {target_amount:,.2f} {unit_b.title()} (at cached offline baseline rates), sir."

        # Length Check
        if unit_a in LENGTH_UNITS and unit_b in LENGTH_UNITS:
            meters = amount * LENGTH_UNITS[unit_a]
            target_amount = meters / LENGTH_UNITS[unit_b]
            return f"{amount:g} {unit_a} is approximately {target_amount:,.2f} {unit_b}, sir."

        # Mass Check
        if unit_a in MASS_UNITS and unit_b in MASS_UNITS:
            grams = amount * MASS_UNITS[unit_a]
            target_amount = grams / MASS_UNITS[unit_b]
            return f"{amount:g} {unit_a} is approximately {target_amount:,.2f} {unit_b}, sir."

        # Data Check
        if unit_a in DATA_UNITS and unit_b in DATA_UNITS:
            bytes_val = amount * DATA_UNITS[unit_a]
            target_amount = bytes_val / DATA_UNITS[unit_b]
            return f"{amount:g} {unit_a} is approximately {target_amount:,.2f} {unit_b}, sir."

        return None
