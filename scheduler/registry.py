from ..registry import ComponentRegistry
from .base import Scheduler

# ComponentRegistry<Scheduler> SCHEDULERS = new ComponentRegistry<>('scheduler');
SCHEDULERS: ComponentRegistry[Scheduler] = ComponentRegistry('scheduler')
