"""数据连接器包：把外部数据源（当前只有 Web，接口留了给 API/数据库的接缝）采集
为带溯源 metadata 的标准化文档，供 ``scripts/crawl_cuit.py`` 落盘为
``data/corpus/web/`` 下的 Markdown 语料，再走现有的摄取流程进知识库。

这个包只负责"采集 + 标准化 + 落盘"，不做切块/向量化——那是
``backend/app/handlers/ingestion_pipeline.py`` 的职责，两者边界清晰，互不
依赖，避免连接器代码意外牵扯 LlamaIndex/Settings 这类需要完整应用环境
（.env、模型配置）才能跑起来的重依赖，保持"只装 httpx/bs4/yaml 就能单测"。
"""

from connectors.base import BaseConnector, CrawledDocument, SourceRef

__all__ = ["BaseConnector", "CrawledDocument", "SourceRef"]
