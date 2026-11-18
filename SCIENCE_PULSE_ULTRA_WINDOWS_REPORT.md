# Science Pulse Ultra Windows Report

Status: PASSED_NATIVE_WINDOWS_60.9S.

The hidden worker hosts the scheduler; Streamlit reruns read local SQLite only. Cold scientific-module imports may exceed 60 seconds, so the worker registration timeout is now 180 seconds. The supervisor keeps UI, API and worker windows hidden.
