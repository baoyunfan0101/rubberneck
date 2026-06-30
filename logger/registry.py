from ..registry import ComponentRegistry
from .base import Logger

# ComponentRegistry<Logger> LOGGERS = new ComponentRegistry<>('logger');
LOGGERS: ComponentRegistry[Logger] = ComponentRegistry('logger')
