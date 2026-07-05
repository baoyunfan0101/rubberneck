from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import cast

from ..downloader import (
    Downloader,
    DownloaderResult,
    DownloaderMiddleware,
    DOWNLOADER_MIDDLEWARES,
    DOWNLOADERS,
)
from ..logger import (
    Logger,
    LoggerAction,
    LogRecord,
    LOGGERS,
)
from ..model import Item, Request, Response
from ..pipeline import (
    Pipeline,
    PipelineResult,
    PipelineMiddleware,
    PIPELINE_MIDDLEWARES,
    PIPELINES,
)
from ..registry import ComponentRegistry, ComponentSpec
from ..scheduler import Scheduler, SCHEDULERS
from ..spider import (
    Spider,
    SpiderResult,
    SpiderMiddleware,
    SPIDER_MIDDLEWARES,
)
from .runtime import ExecutionRuntime
from .state import EngineStats


class Engine:
    def __init__(
        self,
        spider: Spider,
        *,
        logger: Logger | ComponentSpec | str = ComponentSpec('standard'),
        scheduler: Scheduler | ComponentSpec | str = ComponentSpec('sqlite'),
        downloader: Downloader | ComponentSpec | str = ComponentSpec('session_pool'),
        pipeline: Pipeline | ComponentSpec | str = ComponentSpec('sqlite'),
        downloader_middlewares: Iterable[DownloaderMiddleware | ComponentSpec | str] = (
            ComponentSpec('cookies', order=700),
        ),
        spider_middlewares: Iterable[SpiderMiddleware | ComponentSpec | str] = (),
        pipeline_middlewares: Iterable[PipelineMiddleware | ComponentSpec | str] = (),
        downloader_workers: int = 8,
        spider_workers: int = 8,
        pipeline_workers: int = 8,
    ) -> None:
        if downloader_workers < 1:
            raise ValueError('downloader_workers must be at least 1')
        if spider_workers < 1:
            raise ValueError('spider_workers must be at least 1')
        if pipeline_workers < 1:
            raise ValueError('pipeline_workers must be at least 1')

        self.spider = spider

        self.logger = cast(Logger, self._resolve(LOGGERS, logger))  # narrow the resolved component type
        self.scheduler = cast(Scheduler, self._resolve(SCHEDULERS, scheduler))
        self.downloader = cast(Downloader, self._resolve(DOWNLOADERS, downloader))
        self.pipeline = cast(Pipeline, self._resolve(PIPELINES, pipeline))

        self.downloader_middlewares = cast(
            list[DownloaderMiddleware],
            self._resolve_middlewares(DOWNLOADER_MIDDLEWARES, downloader_middlewares),
        )
        self.spider_middlewares = cast(
            list[SpiderMiddleware],
            self._resolve_middlewares(SPIDER_MIDDLEWARES, spider_middlewares),
        )
        self.pipeline_middlewares = cast(
            list[PipelineMiddleware],
            self._resolve_middlewares(PIPELINE_MIDDLEWARES, pipeline_middlewares),
        )

        self.downloader_workers = downloader_workers
        self.spider_workers = spider_workers
        self.pipeline_workers = pipeline_workers

        self.stats = EngineStats()

    def run(self) -> EngineStats:
        runtime = ExecutionRuntime(
            scheduler=self.scheduler,
            stats=self.stats,
            emit=self.emit,
            summary=self.summary,
            run_downloader=self.run_downloader,
            run_spider=self.run_spider,
            run_pipeline=self.run_pipeline,
            downloader_workers=self.downloader_workers,
            spider_workers=self.spider_workers,
            pipeline_workers=self.pipeline_workers,
        )

        try:
            self._open_components()
            runtime.seed(self.spider.start_requests())
            self.emit(LogRecord(
                source='engine',
                action=LoggerAction.START,
                payload=self.summary(),
                level=logging.INFO,
            ))
            runtime.run()
        finally:
            self.emit(LogRecord(
                source='engine',
                action=LoggerAction.FINISH,
                payload=self.summary(),
                level=logging.INFO,
            ))
            self._close_components()
        return self.stats

    def run_downloader(self, request: Request) -> DownloaderResult:
        stack: list[tuple[DownloaderMiddleware, Request]] = []

        for middleware in self.downloader_middlewares:
            request = middleware.process_input(request)
            stack.append((middleware, request))

        output = self.downloader.fetch(request)

        while stack:
            middleware, request = stack.pop()
            output = middleware.process_output(request, output)

        return list(output)  # consume lazy output in worker threads

    def run_spider(self, response: Response) -> SpiderResult:
        stack: list[tuple[SpiderMiddleware, Response]] = []

        for middleware in self.spider_middlewares:
            response = middleware.process_input(response)
            stack.append((middleware, response))

        output = self.spider.parse(response)

        while stack:
            middleware, response = stack.pop()
            output = middleware.process_output(response, output)

        return list(output)  # consume lazy output in worker threads

    def run_pipeline(self, item: Item) -> PipelineResult:
        stack: list[tuple[PipelineMiddleware, Item]] = []

        for middleware in self.pipeline_middlewares:
            item = middleware.process_input(item)
            if not isinstance(item, Item):
                raise TypeError('pipeline middleware input must return an Item')
            stack.append((middleware, item))

        output = self.pipeline.process_item(item)

        while stack:
            middleware, item = stack.pop()
            output = middleware.process_output(item, output)

        return list(output)  # consume lazy output in worker threads

    def _open_components(self) -> None:
        self.scheduler.open()
        for middleware in self.downloader_middlewares:
            middleware.open()
        self.downloader.open()
        for middleware in self.spider_middlewares:
            middleware.open()
        self.spider.open()
        for middleware in self.pipeline_middlewares:
            middleware.open()
        self.pipeline.open()
        self.logger.open()

    def _close_components(self) -> None:
        self.logger.close()
        self.pipeline.close()
        for middleware in reversed(self.pipeline_middlewares):
            middleware.close()
        self.spider.close()
        for middleware in reversed(self.spider_middlewares):
            middleware.close()
        self.downloader.close()
        for middleware in reversed(self.downloader_middlewares):
            middleware.close()
        self.scheduler.close()

    def emit(self, event: LogRecord) -> None:
        self.logger.emit(event)

    def summary(self) -> dict[str, object]:
        return {
            'stats': EngineStats(
                enqueued=self.stats.enqueued,
                filtered=self.stats.filtered,
                done=self.stats.done,
                failed=self.stats.failed,
            ),
            'pending': self.scheduler.pending_count(),
            'leased': self.scheduler.leased_count(),
        }

    @staticmethod
    def _resolve(
        registry: ComponentRegistry,
        value: object,
    ) -> object:
        if isinstance(value, ComponentSpec):
            component = registry.create_spec(value)
        elif isinstance(value, str):
            component = registry.create(value)
        else:
            component = value

        if component is None:
            raise ValueError(f'{registry.category} factory returned None')

        return component

    @classmethod
    def _resolve_middlewares(
        cls,
        registry: ComponentRegistry,
        values: Iterable[object],
    ) -> list[object]:
        resolved: list[tuple[int, int, object]] = []

        for index, value in enumerate(values):
            if isinstance(value, ComponentSpec):
                order = value.order
                component = cls._resolve(registry, value)
            elif isinstance(value, str):
                component = cls._resolve(registry, value)
                order = getattr(component, 'order', 0)
            else:
                component = value
                order = getattr(component, 'order', 0)

            resolved.append((order, index, component))

        return [
            component
            for _, _, component in sorted(resolved, key=lambda entry: entry[:2])
        ]  # sort middlewares by order, then by index
