from ..registry import ComponentRegistry
from .base import Downloader

# ComponentRegistry<Downloader> DOWNLOADERS = new ComponentRegistry<>('downloader');
DOWNLOADERS: ComponentRegistry[Downloader] = ComponentRegistry('downloader')
