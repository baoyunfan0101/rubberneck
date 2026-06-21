from ...registry import ComponentRegistry
from .base import CookieStore

# ComponentRegistry<CookieStore> COOKIE_STORES = new ComponentRegistry<>('cookie store');
COOKIE_STORES: ComponentRegistry[CookieStore] = ComponentRegistry('cookie store')
