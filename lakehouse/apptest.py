from streamlit.testing.v1 import AppTest

at = AppTest.from_file("dashboard/app.py", default_timeout=120)
at.run()
print("exceptions:", len(at.exception))
for ex in at.exception:
    print("EXCEPTION:", ex.message)
    print(ex.stack_trace)
print("errors:", [e.value for e in at.error])
print("tabs:", len(at.tabs))
print("metrics:", [m.label for m in at.metric][:8])
