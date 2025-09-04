# Re-export common entrypoints
from .contracts import (
    EmbedRequest,
    EmbedResult,
    EmbeddingPort,
    EmbeddingError,
    TruncatePolicy,
)
from .adapter_fake import FakeEmbeddingAdapter
from .adapter_openai import OpenAIEmbeddingAdapter
from .service import make_app, router


