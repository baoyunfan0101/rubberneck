from ...registry import ComponentRegistry
from .base import DownloaderMiddleware

# ComponentRegistry<DownloaderMiddleware> DOWNLOADER_MIDDLEWARES = new ComponentRegistry<>('downloader middleware');
DOWNLOADER_MIDDLEWARES: ComponentRegistry[DownloaderMiddleware] = ComponentRegistry('downloader middleware')
