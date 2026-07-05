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
        Run["Engine.run()"]
        CompleteD["Engine._complete_downloader()"]
        CompleteS["Engine._complete_spider()"]
        CompleteP["Engine._complete_pipeline()"]
        HandleEvent["Engine._handle_engine_event()"]
        Check["Engine._check_finished()"]
    end

    subgraph Components[" "]
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
    end


    Start["Spider.start_requests()"] -->|Request| Seed
    Seed -->|Request| Enqueue
    Enqueue --> Dequeue
    Dequeue -->|Request| Run
    Run --> DIn
    DIn --> Downloader
    Downloader --> DOut
    DOut --> CompleteD

    CompleteD -->|Request| DIn
    CompleteD -->|Response| SIn
    CompleteD -->|Failure| Check
    CompleteD -->|EngineEvent| HandleEvent

    SIn --> Spider
    Spider --> SOut
    SOut --> CompleteS

    CompleteS -->|Request| Enqueue
    CompleteS -->|Item| PIn
    CompleteS -->|Failure| Check
    CompleteS -->|EngineEvent| HandleEvent

    PIn --> Pipeline
    Pipeline --> POut
    POut --> CompleteP

    CompleteP -->|Failure| Check
    CompleteP -->|EngineEvent| HandleEvent

    Check --> Done
    Check --> Failed
```

## Minimal Crawler

```python
from rubberneck import Engine, Item, Request, Response, Spider


class ExampleSpider(Spider):
    name = "example"

    def start_requests(self):
        yield Request("https://example.org/")

    def parse(self, response: Response):
        yield Item({"url": response.url, "status": response.status})


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
