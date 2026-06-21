from ..registry import ComponentRegistry
from .middleware import SpiderMiddleware

# ComponentRegistry<SpiderMiddleware> SPIDER_MIDDLEWARES = new ComponentRegistry<>('spider middleware');
SPIDER_MIDDLEWARES: ComponentRegistry[SpiderMiddleware] = ComponentRegistry('spider middleware')
