from ...registry import ComponentRegistry
from .base import SpiderMiddleware

# ComponentRegistry<SpiderMiddleware> SPIDER_MIDDLEWARES = new ComponentRegistry<>('spider middleware');
SPIDER_MIDDLEWARES: ComponentRegistry[SpiderMiddleware] = ComponentRegistry('spider middleware')
