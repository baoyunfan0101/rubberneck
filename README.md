# Rubberneck

Rubberneck is an easy-to-use, multithreaded crawler framework.

## Package Layout

```text
rubberneck/
├── engine/       Runtime, routing
├── model/        Request, Response, Failure
├── scheduler/    Request queue
├── downloader/   Request -> Response
├── spider/       Response -> Item
├── pipeline/     Item consuming
├── logger/       Logger
└── registry/     Component registries
```

## Execution Flow

Rubberneck has six core runtime components: Engine, Scheduler, Downloader, Spider, Pipeline, and Logger.

Scheduler, Downloader, Spider, and Pipeline can run work in parallel; the Engine coordinates them and routes returned
values between components by type.

```mermaid
flowchart TD
    subgraph SchedulerModule["Scheduler"]
        Enqueue["Scheduler.enqueue()"]
        Dequeue["Scheduler.dequeue()"]
        Done["Scheduler.mark_done()"]
        Failed["Scheduler.mark_failed()"]
    end

    subgraph EngineModule["Engine"]
        Seed["Engine.seed()"]
        Check["Engine.check_finished()"]
    end

    subgraph DownloaderModule["Downloader"]
        DIn["DownloaderMiddleware.process_input()"]
        Downloader["Downloader.fetch()"]
        DOut["DownloaderMiddleware.process_output()"]
    end

    subgraph SpiderModule["Spider"]
        SIn["SpiderMiddleware.process_input()"]
        Spider["Spider.parse()"]
        SOut["SpiderMiddleware.process_output()"]
    end

    subgraph PipelineModule["Pipeline"]
        PIn["PipelineMiddleware.process_input()"]
        Pipeline["Pipeline.process_item()"]
        POut["PipelineMiddleware.process_output()"]
    end

    Start["Spider.start_requests()"] -->|Request| Seed
    Seed -->|Request| Enqueue
    Enqueue --> Dequeue
    Dequeue -->|Request| DIn
    DIn --> Downloader
    Downloader --> DOut

    DOut -->|Request| DIn
    DOut -->|Response| SIn
    DOut -->|Failure| Failed
    DOut -->|LoggerEvent| Logger["logger"]
    DOut --> Check

    SIn --> Spider
    Spider --> SOut

    SOut -->|Request| Enqueue
    SOut -->|Item| PIn
    SOut -->|LoggerEvent| Logger
    SOut --> Check

    PIn --> Pipeline
    Pipeline --> POut

    POut -->|Item| Logger
    POut -->|LoggerEvent| Logger
    POut --> Check

    Check -->|no running work and no error| Done
    Check -->|no running work and error| Failed

    Done --> Logger
    Failed --> Logger
```

## Minimal Crawler

```python
from rubberneck import Engine, Request, Response, Spider


class ExampleSpider(Spider):
    name = "example"

    def start_requests(self):
        yield Request("https://example.org/")

    def parse(self, response: Response):
        yield {"url": response.url, "status": response.status}


Engine(ExampleSpider()).run()
```

## Components

Runtime components can be replaced by passing an instance, a registry name, or a `ComponentSpec`.

```python
from rubberneck import ComponentSpec, Engine

engine = Engine(
    spider,
    logger='logger'
scheduler = ComponentSpec('sqlite', {'path': './data'}),
)
```

## Installation

```sh
python -m pip install .
```
