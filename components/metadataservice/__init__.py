# MetadataService package init (v0.1)
from .service import router, create_app
from .contracts import (
    Envelope,
    ExtractRequest,
    ExtractResponse,
    MetadataRecord,
    Stats,
    ErrorEnvelope,
)

---

```python
