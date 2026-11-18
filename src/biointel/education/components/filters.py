from __future__ import annotations
from datetime import date, timedelta
from typing import Any
from .._streamlit_compat import st

def dashboard_filters(*, key: str, sessions: list[str] | None = None, subjects: list[str] | None = None) -> dict[str, Any]:
    today=date.today()
    with st.container(border=True):
        st.caption("Dashboard filters")
        start,end=st.date_input("Date range", value=(today-timedelta(days=90),today), key=f"{key}_dates")
        session=st.selectbox("Academic session", sessions or ["Current"], key=f"{key}_session")
        subject=st.selectbox("Subject", ["All",*(subjects or [])], key=f"{key}_subject")
    return {"date_start":start.isoformat(),"date_end":end.isoformat(),"academic_session":session,"subject":subject}