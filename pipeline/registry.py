from ..registry import ComponentRegistry
from .base import Pipeline

# ComponentRegistry<Pipeline> PIPELINES = new ComponentRegistry<>('pipeline');
PIPELINES: ComponentRegistry[Pipeline] = ComponentRegistry('pipeline')
