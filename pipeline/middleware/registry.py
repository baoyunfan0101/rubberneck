from ...registry import ComponentRegistry
from .base import PipelineMiddleware

# ComponentRegistry<PipelineMiddleware> PIPELINE_MIDDLEWARES = new ComponentRegistry<>('pipeline middleware');
PIPELINE_MIDDLEWARES: ComponentRegistry[PipelineMiddleware] = ComponentRegistry('pipeline middleware')
