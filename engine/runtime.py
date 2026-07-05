from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
import logging
from queue import Queue
from typing import Any

from ..downloader import DownloaderResult
from ..logger import LoggerAction, LogRecord
from ..model import EngineAction, EngineEvent, Failure, Item, Request, Response
from ..pipeline import PipelineResult
from ..scheduler import Scheduler
from ..spider import SpiderResult
from .state import EngineStats, WorkOrder


class _WorkerMessageKind(str, Enum):
    VALUE = 'value'
    DONE = 'done'
    ERROR = 'error'


class _WorkerSource(str, Enum):
    DOWNLOADER = 'downloader'
    SPIDER = 'spider'
    PIPELINE = 'pipeline'


@dataclass(frozen=True)
class _WorkerMessage:
    kind: _WorkerMessageKind  # value, done, error
    source: _WorkerSource  # downloader, spider, pipeline
    order: WorkOrder
    value: object = None
    error: BaseException | None = None
    succeeded: bool = True


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

        # workers stream results into worker_messages instead of returning, so futures return None
        self.downloader_running: dict[Future[None], WorkOrder] = {}
        self.spider_running: dict[Future[None], WorkOrder] = {}
        self.pipeline_running: dict[Future[None], WorkOrder] = {}
        self.worker_messages: Queue[_WorkerMessage] = Queue()

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
                try:
                    # fill downloader inflight
                    while (
                        not (self.stop_gracefully_requested or self.stop_now_requested)
                        and len(self.downloader_running) < self.target_downloader_inflight
                    ):
                        request = self.scheduler.dequeue()
                        if request is None:
                            break

                        # scheduler -->|Request| downloader
                        order = WorkOrder(request)
                        self._submit_downloader(request, order)
                except KeyboardInterrupt:
                    if request is not None:
                        if order is None:
                            order = WorkOrder(request)
                        if order.is_idle():
                            self._submit_downloader(request, order)
                    self._request_stop_gracefully('keyboard interrupt')
                    continue

                if not self._has_running_work():
                    continue

                try:
                    message = self.worker_messages.get()
                except KeyboardInterrupt:
                    self._request_stop_gracefully('keyboard interrupt')
                    continue

                self._handle_worker_message(message)

        finally:
            wait_for_workers = not self.stop_now_requested
            self.pipeline_executor.shutdown(wait=wait_for_workers, cancel_futures=True)
            self.spider_executor.shutdown(wait=wait_for_workers, cancel_futures=True)
            self.downloader_executor.shutdown(wait=wait_for_workers, cancel_futures=True)
            if self.stop_gracefully_requested or self.stop_now_requested:
                self._emit_stopped()

    def _handle_worker_message(self, message: _WorkerMessage) -> None:
        if message.kind == _WorkerMessageKind.VALUE:
            if self.stop_now_requested or message.order.acked:
                return
            self._route_value(message.source, message.order, message.value)
        elif message.kind == _WorkerMessageKind.DONE:
            if self._finish_task(message.source, message.order):
                if (
                    message.source == _WorkerSource.PIPELINE
                    and message.succeeded
                    and not message.order.acked
                ):
                    message.order.count('processed')
                self._check_finished(message.order)
        elif message.kind == _WorkerMessageKind.ERROR:
            if self._finish_task(message.source, message.order):
                assert message.error is not None
                if isinstance(message.error, KeyboardInterrupt):
                    self._request_stop_gracefully('keyboard interrupt')
                    self._check_finished(message.order)
                else:
                    self._record_exception(message.order, message.error, message.source)
        else:
            self._record_exception(
                message.order,
                RuntimeError(f'unknown worker message: {message.kind!r}'),
                message.source,
            )

    def _route_value(self, source: _WorkerSource, order: WorkOrder, value: object) -> None:
        if source == _WorkerSource.DOWNLOADER:
            self._route_downloader_value(order, value)
        elif source == _WorkerSource.SPIDER:
            self._route_spider_value(order, value)
        elif source == _WorkerSource.PIPELINE:
            self._route_pipeline_value(order, value)
        else:
            self._record_exception(order, RuntimeError(f'unknown worker source: {source!r}'), source)

    def _route_downloader_value(self, order: WorkOrder, value: object) -> None:
        if isinstance(value, EngineEvent):
            self._handle_engine_event(order, value)
        elif isinstance(value, Request):
            self._submit_downloader(value, order)
        elif isinstance(value, Response):
            self._submit_spider(value, order)
        elif isinstance(value, Failure):
            self._record_failure(order, value, _WorkerSource.DOWNLOADER)
        else:
            self._record_exception(
                order,
                TypeError('downloader must return Request, Response, Failure, or EngineEvent'),
                _WorkerSource.DOWNLOADER,
            )

    def _route_spider_value(self, order: WorkOrder, value: object) -> None:
        if isinstance(value, EngineEvent):
            self._handle_engine_event(order, value)
        elif isinstance(value, Request):
            accepted = self.scheduler.enqueue(value)
            if accepted:
                self.stats.enqueued += 1
                order.count('enqueued')
            else:
                self.stats.filtered += 1
                order.count('filtered')
        elif isinstance(value, Item):
            self._submit_pipeline(value, order)
        elif isinstance(value, Failure):
            self._record_failure(order, value, _WorkerSource.SPIDER)
        else:
            self._record_exception(
                order,
                TypeError('spider output must be a Request, Item, Failure, or EngineEvent'),
                _WorkerSource.SPIDER,
            )

    def _route_pipeline_value(self, order: WorkOrder, value: object) -> None:
        if isinstance(value, EngineEvent):
            self._handle_engine_event(order, value)
        elif isinstance(value, Failure):
            self._record_failure(order, value, _WorkerSource.PIPELINE)
        else:
            self._record_exception(
                order,
                TypeError('pipeline must return Failure or EngineEvent'),
                _WorkerSource.PIPELINE,
            )

    def _submit_downloader(self, request: Request, order: WorkOrder) -> None:
        future = self.downloader_executor.submit(
            self._drain_worker,
            source=_WorkerSource.DOWNLOADER,
            order=order,
            run_component=self.run_downloader,
            input_value=request,
        )
        order.downloaders += 1
        self.downloader_running[future] = order

    def _submit_spider(self, response: Response, order: WorkOrder) -> None:
        future = self.spider_executor.submit(
            self._drain_worker,
            source=_WorkerSource.SPIDER,
            order=order,
            run_component=self.run_spider,
            input_value=response,
        )
        order.spiders += 1
        self.spider_running[future] = order

    def _submit_pipeline(self, item: Item, order: WorkOrder) -> None:
        future = self.pipeline_executor.submit(
            self._drain_worker,
            source=_WorkerSource.PIPELINE,
            order=order,
            run_component=self.run_pipeline,
            input_value=item,
        )
        order.pipelines += 1
        self.pipeline_running[future] = order

    def _drain_worker(
        self,
        source: _WorkerSource,
        order: WorkOrder,
        run_component: Callable[[Any], Iterable[Any]],
        input_value: object,
    ) -> None:
        succeeded = True
        try:
            for value in run_component(input_value):  # consume the output generator returned by run_component()
                if isinstance(value, Failure):
                    succeeded = False
                self.worker_messages.put(_WorkerMessage(
                    kind=_WorkerMessageKind.VALUE,
                    source=source,
                    order=order,
                    value=value,
                ))
        except BaseException as error:
            self.worker_messages.put(_WorkerMessage(
                kind=_WorkerMessageKind.ERROR,
                source=source,
                order=order,
                error=error,
            ))
        else:
            self.worker_messages.put(_WorkerMessage(
                kind=_WorkerMessageKind.DONE,
                source=source,
                order=order,
                succeeded=succeeded,
            ))

    def _finish_task(self, source: _WorkerSource, order: WorkOrder) -> bool:
        running = self._running_tasks(source)
        future = self._pop_running_task(running, order)
        if future is None:
            return False

        if source == _WorkerSource.DOWNLOADER:
            order.downloaders -= 1
        elif source == _WorkerSource.SPIDER:
            order.spiders -= 1
        elif source == _WorkerSource.PIPELINE:
            order.pipelines -= 1
        else:
            self._record_exception(order, RuntimeError(f'unknown worker source: {source!r}'), source)
            return False
        return True

    @staticmethod
    def _pop_running_task(
        running: dict[Future[None], WorkOrder],
        order: WorkOrder,
    ) -> Future[None] | None:
        for future, running_order in list(running.items()):
            if running_order is order and future.done():
                running.pop(future)
                return future
        for future, running_order in list(running.items()):
            if running_order is order:
                running.pop(future)
                return future
        return None

    def _running_tasks(self, source: _WorkerSource) -> dict[Future[None], WorkOrder]:
        if source == _WorkerSource.DOWNLOADER:
            return self.downloader_running
        if source == _WorkerSource.SPIDER:
            return self.spider_running
        if source == _WorkerSource.PIPELINE:
            return self.pipeline_running
        return {}

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

    def _record_exception(
        self,
        order: WorkOrder,
        error: BaseException,
        component: str | _WorkerSource,
    ) -> None:
        if order.acked:
            return

        order.error = error
        payload = {
            'component': component.value if isinstance(component, _WorkerSource) else component,
            'request': order.request,
            'error': error,
        }
        order.collect(payload)
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.FAILED,
            payload=order.payload,
            level=logging.ERROR,
        ))
        self._check_finished(order)

    def _record_failure(
        self,
        order: WorkOrder,
        failure: Failure,
        component: str | _WorkerSource,
    ) -> None:
        if order.acked:
            return

        order.error = failure.exception
        payload = {
            'component': component.value if isinstance(component, _WorkerSource) else component,
            'request': order.request,
            'failure': failure,
        }
        order.collect(payload)
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.FAILED,
            payload=order.payload,
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
        error = order.error
        if not isinstance(error, Exception):
            error = RuntimeError(str(error))
        self.scheduler.mark_failed(order.request, error)
        self.stats.failed += 1
        self._emit_done(order)

    def _emit_done(self, order: WorkOrder) -> None:
        self.emit(LogRecord(
            source='engine',
            action=LoggerAction.DONE,
            payload=order.payload,
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
