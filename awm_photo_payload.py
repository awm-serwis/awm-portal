"""R407: bounded photo payload, shared by server and authorized desktop."""
import base64
import binascii

MAX_PHOTOS = 4
MAX_BYTES = 600_000


def decode_photos(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_PHOTOS:
        raise ValueError('Dodaj od 1 do 4 zdjęć.')
    result = []
    for item in value:
        if not isinstance(item, str) or len(item) > 4 * ((MAX_BYTES + 2) // 3):
            raise ValueError('Zdjęcie jest za duże lub nieprawidłowe.')
        try:
            data = base64.b64decode(item, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('Nieprawidłowy zapis zdjęcia.') from None
        if len(data) > MAX_BYTES or len(data) < 4 or not data.startswith(b'\xff\xd8\xff') or not data.endswith(b'\xff\xd9'):
            raise ValueError('Wymagane jest zdjęcie JPEG do 600 kB.')
        result.append(data)
    return result
