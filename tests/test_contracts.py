import pytest
from pydantic import ValidationError

from components.vectorstoreadapter.models import VectorRecord, DNFFilter, FilterCondition


def test_vectorrecord_validation():
    r = VectorRecord(id="a", vector=[0.1, 0.2, 0.3], metadata={"k": 1})
    assert r.id == "a"
    with pytest.raises(ValidationError):
        VectorRecord(id="", vector=[0.1], metadata={})
    with pytest.raises(ValidationError):
        VectorRecord(id="x", vector=[float("nan")], metadata={})


def test_dnf_filter_structure():
    flt = DNFFilter(groups=[[FilterCondition(field="k", op="eq", value=1)]])
    assert len(flt.groups) == 1

---


