"""Validated collection days shared by serving, training and retention."""
import datetime as dt


def valid_day(value):
    if len(value) != 8 or not value.isascii() or not value.isdecimal():
        return False
    try:
        dt.date(int(value[:4]), int(value[4:6]), int(value[6:]))
        return True
    except ValueError:
        return False


def day_folders(root):
    return sorted(p for p in root.glob('*') if valid_day(p.name) and p.is_dir())


def day_caches(root, route=None):
    routes = (route,) if route else ('sb02', 'jr03')
    return sorted(p for p in root.glob('*_*.json')
                  if p.stem[9:] in routes and p.stem[8:9] == '_' and valid_day(p.stem[:8]) and p.is_file())
