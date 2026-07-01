from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import logging

from ..downloader import DownloaderResult
from ..logger import LoggerAction, LoggerEvent
from ..model import Failure, Request, Response
from ..pipeline import PipelineResult
from ..scheduler import Scheduler
from ..spider import SpiderResult
from .state import EngineStats, WorkOrder


class ExecutionRuntime:
    def __init__(
        self,
        *,
        scheduler: Scheduler,
        stats: EngineStats,
        emit: Callable[[LoggerEvent], None],
        summary: Callable[[], dict[str, object]],
        run_downloader: Callable[[Request], DownloaderResult],
        run_spider: Callable[[Response], SpiderResult],
        run_pipeline: Callable[[Mapping[str, object]], PipelineResult],
        downloader_workers: int,
        spider_workers: int,
        pipeline_workers: int,
    ) -> None:
        self.scheduler = scheduler
        self.stats = stats
        self.emit = emit
        self.summary = summary

        self.downloader_running: dict[Future[DownloaderResult], WorkOrder] = {}
        self.spider_running: dict[Future[SpiderResult], WorkOrder] = {}
        self.pipeline_running: dict[Future[PipelineResult], WorkOrder] = {}

        self.downloader_executor = ThreadPoolExecutor(
            max_workers=downloader_workers,
            thread_name_prefix='rubberneck-downloader',
        )
        self.spider_executor = ThreadPoolExecutor(
            max_workers=spider_workers,
            thread_name_prefix='rubberneck-spider',
        )
        self.pipeline_executor = ThreadPoolExecutor(
            max_workers=pipeline_workers,
            thread_name_prefix='rubberneck-pipeline',
        )

        self.run_downloader = run_downloader
        self.run_spider = run_spider
        self.run_pipeline = run_pipeline

        self.target_downloader_inflight = downloader_workers

    def seed(self, requests: Iterable[Request]) -> None:
        for request in requests:
            accepted = self.scheduler.enqueue(request)
            if accepted:
                self.stats.enqueued += 1
            else:
                self.stats.filtered += 1

    def run(self) -> None:
        try:
            while self.scheduler.has_pending() or self._has_running_work():
                # fill downloader inflight
                while len(self.downloader_running) < self.target_downloader_inflight:
                    request = self.scheduler.dequeue()
                    if request is None:
                        break

                    # router: scheduler -> downloader
                    order = WorkOrder(request)
                    future = self.downloader_executor.submit(self.run_downloader, request)
                    order.downloaders += 1
                    self.downloader_running[future] = order

                if not self._has_running_work():
                    continue

                completed, _ = wait(
                    {
                        *self.downloader_running,
                        *self.spider_running,
                        *self.pipeline_running,
                    },
                    return_when=FIRST_COMPLETED,
                )

                for future in completed:
                    # router: downloader -> downloader / spider / logger
                    if future in self.downloader_running:

                        order = self.downloader_running.pop(future)
                        order.downloaders -= 1

                        try:
                            output = future.result()
                        except Exception as error:
                            self._mark_failed(order, error, 'downloader')
                            continue

                        if order.acked:
                            continue

                        try:
                            for value in output:
                                if isinstance(value, LoggerEvent):
                                    order.collect(value)
                                    self.emit(value)

                                elif isinstance(value, Request):
                                    next_future = self.downloader_executor.submit(
                                        self.run_downloader,
                                        value,
                                    )
                                    order.downloaders += 1
                                    self.downloader_running[next_future] = order

                                elif isinstance(value, Response):
                                    next_future = self.spider_executor.submit(
                                        self.run_spider,
                                        value,
                                    )
                                    order.spiders += 1
                                    self.spider_running[next_future] = order

                                elif isinstance(value, Failure):
                                    self._mark_failed(order, value.exception, 'downloader')
                                    break

                                else:
                                    raise TypeError(
                                        'downloader must return Request, Response, Failure, or LoggerEvent'
                                    )
                        except Exception as error:
                            self._mark_failed(order, error, 'downloader')
                            continue

                        self._mark_done_if_idle(order)

                    # router: spider -> scheduler / pipeline / logger
                    elif future in self.spider_running:

                        order = self.spider_running.pop(future)
                        order.spiders -= 1

                        try:
                            output = future.result()
                        except Exception as error:
                            self._mark_failed(order, error, 'spider')
                            continue

                        if order.acked:
                            continue

                        try:
                            for value in output:
                                if isinstance(value, LoggerEvent):
                                    order.collect(value)
                                    self.emit(value)

                                elif isinstance(value, Request):
                                    accepted = self.scheduler.enqueue(value)
                                    if accepted:
                                        self.stats.enqueued += 1
                                        order.enqueued += 1
                                    else:
                                        self.stats.filtered += 1
                                        order.filtered += 1

                                elif isinstance(value, Mapping):
                                    next_future = self.pipeline_executor.submit(
                                        self.run_pipeline,
                                        value,
                                    )
                                    order.pipelines += 1
                                    self.pipeline_running[next_future] = order

                                else:
                                    raise TypeError(
                                        'spider output must be a Request, mapping-like item, or LoggerEvent'
                                    )
                        except Exception as error:
                            self._mark_failed(order, error, 'spider')
                            continue

                        self._mark_done_if_idle(order)

                    # router: pipeline processed / failed
                    elif future in self.pipeline_running:

                        order = self.pipeline_running.pop(future)
                        order.pipelines -= 1

                        try:
                            output = future.result()
                        except Exception as error:
                            self._mark_failed(order, error, 'pipeline')
                            continue

                        if order.acked:
                            continue

                        try:
                            for value in output:
                                if isinstance(value, LoggerEvent):
                                    order.collect(value)
                                    self.emit(value)

                                elif isinstance(value, Mapping):
                                    order.processed += 1
                                    self.emit(LoggerEvent('pipeline', payload=value))

                                else:
                                    raise TypeError(
                                        'pipeline must return mapping-like item or LoggerEvent'
                                    )
                        except Exception as error:
                            self._mark_failed(order, error, 'pipeline')
                            continue

                        self._mark_done_if_idle(order)

        finally:
            self.pipeline_executor.shutdown()
            self.spider_executor.shutdown()
            self.downloader_executor.shutdown()

    def _mark_done_if_idle(self, order: WorkOrder) -> None:
        if order.acked or not order.is_idle():
            return

        order.acked = True
        if order.error is not None:
            self.scheduler.mark_failed(order.request, order.error)
            self.stats.failed += 1
        else:
            self.scheduler.mark_done(order.request)
            self.stats.done += 1
        self._emit_done(order)

    def _mark_failed(self, order: WorkOrder, error: Exception, source: str) -> None:
        if order.acked:
            return

        order.error = error
        event = LoggerEvent(
            source,
            action=LoggerAction.FAILED,
            payload={'request': order.request, 'error': error},
            level=logging.ERROR,
        )
        order.collect(event)
        self.emit(event)
        self._mark_done_if_idle(order)

    def _emit_done(self, order: WorkOrder) -> None:
        self.emit(LoggerEvent(
            'engine',
            action=LoggerAction.DONE,
            payload={'order': order},
        ))
        self.emit(LoggerEvent(
            'engine',
            action=LoggerAction.SUMMARY,
            payload=self.summary(),
        ))

    def _has_running_work(self) -> bool:
        return bool(
            self.downloader_running
            or self.spider_running
            or self.pipeline_running
        )
