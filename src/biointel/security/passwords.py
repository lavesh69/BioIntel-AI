from __future__ import annotations
import base64,binascii,hashlib,hmac,os
from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

SCHEME='argon2id'; LEGACY_SCHEME='pbkdf2_sha256'; DEFAULT_ITERATIONS=600_000

def _legacy_hash(password:str,iterations:int,salt:bytes)->str:
    if iterations<310_000: raise ValueError('PBKDF2 iteration count is below the supported security floor.')
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,iterations)
    return '$'.join([LEGACY_SCHEME,str(iterations),base64.urlsafe_b64encode(salt).decode().rstrip('='),base64.urlsafe_b64encode(digest).decode().rstrip('=')])

def hash_password(password:str,*,iterations:int|None=None,salt:bytes|None=None)->str:
    """Hash new passwords with Argon2id; explicit legacy parameters retain migration compatibility."""
    if len(password)<12: raise ValueError('Password must contain at least 12 characters.')
    if iterations is not None or salt is not None: return _legacy_hash(password,iterations or DEFAULT_ITERATIONS,salt or os.urandom(16))
    return Argon2id(salt=os.urandom(16),length=32,iterations=3,lanes=4,memory_cost=64*1024).derive_phc_encoded(password.encode())

def _decode(value:str)->bytes: return base64.urlsafe_b64decode(value+'='*(-len(value)%4))
def _verify_legacy(password:str,encoded:str)->bool:
    try:
        scheme,iterations_text,salt_text,digest_text=encoded.split('$',3)
        if scheme!=LEGACY_SCHEME: return False
        iterations=int(iterations_text)
        if iterations<310_000: return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),_decode(salt_text),iterations)
        return hmac.compare_digest(actual,_decode(digest_text))
    except (TypeError,ValueError,binascii.Error): return False

def verify_password(password:str,encoded:str)->bool:
    if encoded.startswith('$argon2id$'):
        try: Argon2id.verify_phc_encoded(password.encode(),encoded); return True
        except (InvalidKey,ValueError,TypeError): return False
    return _verify_legacy(password,encoded)

def needs_rehash(encoded:str)->bool: return not encoded.startswith('$argon2id$')
