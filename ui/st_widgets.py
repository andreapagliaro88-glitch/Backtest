"""Helper Streamlit condivisi."""
from __future__ import annotations


def dataframe_kwargs(n_rows: int, *, height: int = 700, min_rows: int = 15) -> dict:
    """kwargs extra per st.dataframe (solo height, se serve scroll)."""
    if n_rows > min_rows:
        return {"height": height}
    return {}
