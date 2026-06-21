from ..registry import ComponentRegistry
from .base import ItemPipeline

# ComponentRegistry<ItemPipeline> PIPELINES = new ComponentRegistry<>('pipeline');
PIPELINES: ComponentRegistry[ItemPipeline] = ComponentRegistry('pipeline')
