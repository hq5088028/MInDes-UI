import re

def clean_excel_string(val):
    if isinstance(val, str):
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', val)
    return val