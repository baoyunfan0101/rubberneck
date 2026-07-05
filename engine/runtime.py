from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import logging

from ..downloader import DownloaderResult
from ..logger import LoggerAction, LogRecord
from ..model import EngineAction, EngineEvent, Failure, Item, Request, Response
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
        emit: Callable[[LogRecord], None],
        summary: Callable[[], dict[str, object]],
        run_downloader: Callable[[Request], DownloaderResult],
        run_spider: Callable[[Response], SpiderResult],
        run_pipeline: Callable[[Item], PipelineResult],
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
        self.stop_gracefully_requested = False
        self.stop_now_requested = False
        self.stop_mode = ''

    def seed(self, requests: Iterable[Request]) -> None:
        for request in requests:
            accepted = self.scheduler.enqueue(request)
            if accepted:
                self.stats.enqueued += 1
            else:
                self.stats.filtered += 1

    def run(self) -> None:
        try:
            while (
                (
                    not (self.stop_gracefully_requested or self.stop_now_requested)
                    and self.scheduler.has_pending()
                )
                or self._has_running_work()
            ):
                request: Request | None = None
                order: WorkOrder | None = None
                future: Future[DownloaderResult] | None = None
                try:
                    # fill downloader inflight
                    while (
                        not (self.stop_gracefully_requested or self.stop_now_requested)
                        and len(self.downloader_running) < self.target_downloader_inflight
                    ):
                        request = self.scheduler.dequeue()
                        if request is None:
                            break

                        # router: scheduler -> downloader
                        order = WorkOrder(request)
                        future = self.downloader_executor.submit(self.run_downloader, request)
                        order.downloaders += 1
                        self.downloader_running[future] = order
                except KeyboardInterrupt:
                    if request is not None:
                        if order is None:
                            order = WorkOrder(request)
                        if future is None:
                            future = self.downloader_executor.submit(self.run_downloader, request)
                        if future not in self.downloader_running:
                            order.downloaders += 1
                            self.downloader_running[future] = order
                    self._request_stop_gracefully('keyboard interrupt')
                    continue

                if not self._has_running_work():
                    continue

                try:
                    completed, _ = wait(
                        {
                            *self.downloader_running,
                            *self.spider_running,
                            *self.pipeline_running,
                        },
                        return_when=FIRST_COMPLETED,
                    )
                except KeyboardInterrupt:
                    self._request_stop_gracefully('keyboard interrupt')
                    continue

                for future in completed:
                    if self.stop_now_requested:
                        self.downloader_running.pop(future, None)
                        self.spider_running.pop(future, None)
                        self.pipeline_running.pop(future, None)
                        continue

                    if future in self.downloader_running:
                        self._complete_downloader(future)
                    elif future in self.spider_running:
                        self._complete_spider(future)
                    elif future in self.pipeline_running:
                        self._complete_pipeline(future)

        finally:
            wait_for_workers = not self.stop_now_requested
            self.pipeline_executor.shutdown(wait=wait_for_workers, cancel_futures=True)
            self.spider_executor.shutdown(wait=wait_for_workers, cancel_futures=True)
            self.downloader_executor.shutdown(wait=wait_for_workers, cancel_futures=True)
            if self.stop_gracefully_requested or self.stop_now_requested:
                self._emit_stopped()

    def _complete_downloader(self, future: Future[DownloaderResult]) -> None:
        order = self.downloader_running.pop(future)
        order.downloaders -= 1

        try:
            output = future.result()
        except KeyboardInterrupt:
            self._request_stop_gracefully('keyboard interrupt')
            self._check_finished(order)
            return
        except Exception as error:
            self._record_exception(order, error, 'downloader')
            return

        if order.acked:
            return

        try:
            for value in output:
                if isinstance(value, EngineEvent):
                    self._handle_engine_event(order, value)
                    if self.stop_now_requested:
                        break

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
                    self._record_failure(order, value, 'downloader')
                    break

                else:
                    raise TypeError(
                        'downloader must return Request, Response, Failure, or EngineEvent'
                    )
        except KeyboardInterrupt:
            self._request_stop_gracefully('keyboard interrupt')
            self._check_finished(order)
            return
        except Exception as error:
            self._record_exception(order, error, 'downloader')
            return

        self._check_finished(order)

    def _complete_spider(self, future: Future[SpiderResult]) -> None:
        order = self.spider_running.pop(future)
        order.spiders -= 1

        try:
            output = future.result()
        except KeyboardInterrupt:
            self._request_stop_gracefully('keyboard interrupt')
            self._check_finished(order)
            return
        except Exception as error:
            self._record_exception(order, error, 'spider')
            return

        if order.acked:
            return

        try:
            for value in output:
                if isinstance(value, EngineEvent):
                    self._handle_engine_event(order, value)
                    if self.stop_now_requested:
                        break

                elif isinstance(value, Request):
                    accepted = self.scheduler.enqueue(value)
                    if accepted:
                        self.stats.enqueued += 1
                        order.enqueued += 1
                    else:
                        self.stats.filtered += 1
                        order.filtered += 1

                elif isinstance(value, Item):
                    next_future = self.pipeline_executor.submit(
                        self.run_pipeline,
                        value,
                    )
                    order.pipelines += 1
                    self.pipeline_running[next_future] = order

                elif isinstance(value, Failure):
                    self._record_failure(order, value, 'spider')
                    break

                else:
                    raise TypeError(
                        'spider output must be a Request, Item, Failure, or EngineEvent'
                    )
        except KeyboardInterrupt:
            self._request_stop_gracefully('keyboard interrupt')
            self._check_finished(order)
            return
        except Exception as error:
            self._record_exception(order, error, 'spider')
            return

        self._check_finished(order)

    def _complete_pipeline(self, future: Future[PipelineResult]) -> None:
        order = self.pipeline_running.pop(future)
        order.pipelines -= 1

        try:
            output = future.result()
        except KeyboardInterrupt:
            self._request_stop_gracefully('keyboard interrupt')
            self._check_finished(order)
            return
        except Exception as error:
            self._record_exception(order, error, 'pipeline')
            return

        if order.acked:
            return

        try:
            for value in output:
                if isinstance(value, EngineEvent):
                    self._handle_engine_event(order, value)
                    if self.stop_now_requested:
                        break

                elif isinstance(value, Failure):
                    self._record_failure(order, value, 'pipeline')
                    break

                else:
                    raise TypeError(
                        'pipeline must return Failure or EngineEvent'
                    )
        except KeyboardInterrupt:
            self._request_stop_gracefully('keyboard interrupt')
            self._check_finished(order)
            return
        except Exception as error:
            self._record_exception(order, error, 'pipeline')
            return

        if order.acked:
            return

        order.processed += 1
        self._check_finished(order)

    def _check_finished(self, order: WorkOrder) -> None:
        if order.acked or not order.is_idle():
            return

        if order.error is not None:
            self._mark_failed(order)
        else:
            self._mark_done(order)

    def _handle_engine_event(self, order: WorkOrder, event: EngineEvent) -> None:
        if event.action == EngineAction.COLLECT:
            order.collect(event.payload)
        elif event.action == EngineAction.STOP_GRACEFULLY:
            self._request_stop_gracefully(event.payload.get('reason', 'stop requested'))
        elif event.action == EngineAction.STOP_NOW:
            self._request_stop_now(order, event.payload)
        elif event.action != EngineAction.NONE:
            raise ValueError(f'unknown engine action: {event.action!r}')

        if event.log is not None:
            self.emit(event.log)

    def _request_stop_gracefully(self, reason: object) -> None:
        if self.stop_gracefully_requested or self.stop_now_requested:
            return
        self.stop_gracefully_requested = True
        self.stop_mode = 'gracefully'
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.STOPPING,
            payload={
                'mode': self.stop_mode,
                'reason': reason,
            },
            level=logging.WARNING,
        ))

    def _request_stop_now(
        self,
        current_order: WorkOrder,
        payload: Mapping[str, object],
    ) -> None:
        if not self.stop_now_requested:
            self.emit(LogRecord(
                source='engine',
                action=LoggerAction.STOPPING,
                payload={
                    'mode': 'now',
                    'reason': payload.get('reason', 'stop requested'),
                },
                level=logging.WARNING,
            ))
        self.stop_now_requested = True
        self.stop_gracefully_requested = True
        self.stop_mode = 'now'
        self._fail_order(current_order, payload)

        reason = payload.get('reason', 'stop requested')
        if isinstance(reason, Exception):
            error = reason
        else:
            error = RuntimeError(str(reason))

        orders: dict[int, WorkOrder] = {}
        for order in (
                *self.downloader_running.values(),
                *self.spider_running.values(),
                *self.pipeline_running.values(),
        ):
            orders[id(order)] = order

        for future in (
                *self.downloader_running,
                *self.spider_running,
                *self.pipeline_running,
        ):
            future.cancel()

        self.downloader_running.clear()
        self.spider_running.clear()
        self.pipeline_running.clear()

        for order in orders.values():
            self._fail_order(order, {'reason': error})

    def _emit_stopped(self) -> None:
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.STOPPED,
            payload={
                'mode': self.stop_mode,
                'summary': self.summary(),
            },
        ))

    def _fail_order(
        self,
        order: WorkOrder,
        payload: Mapping[str, object],
    ) -> None:
        if order.acked:
            return
        reason = payload.get('reason', 'stop requested')
        if isinstance(reason, Exception):
            order.error = reason
        else:
            order.error = RuntimeError(str(reason))
        self._mark_failed(order)

    def _record_exception(self, order: WorkOrder, error: Exception, component: str) -> None:
        if order.acked:
            return

        order.error = error
        payload = {
            'component': component,
            'request': order.request,
            'error': error,
        }
        order.collect(payload)
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.FAILED,
            payload=payload,
            level=logging.ERROR,
        ))
        self._check_finished(order)

    def _record_failure(
        self,
        order: WorkOrder,
        failure: Failure,
        component: str,
    ) -> None:
        if order.acked:
            return

        order.error = failure.exception
        payload = {
            'component': component,
            'request': order.request,
            'failure': failure,
        }
        order.collect(payload)
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.FAILED,
            payload=payload,
            level=logging.ERROR,
        ))
        self._check_finished(order)

    def _mark_done(self, order: WorkOrder) -> None:
        order.acked = True
        self.scheduler.mark_done(order.request)
        self.stats.done += 1
        self._emit_done(order)

    def _mark_failed(self, order: WorkOrder) -> None:
        order.acked = True
        self.scheduler.mark_failed(order.request, order.error)
        self.stats.failed += 1
        self._emit_done(order)

    def _emit_done(self, order: WorkOrder) -> None:
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.DONE,
            payload={'order': order},
        ))
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.SUMMARY,
            payload=self.summary(),
        ))

    def _has_running_work(self) -> bool:
        return bool(
            self.downloader_running
            or self.spider_running
            or self.pipeline_running
        )
