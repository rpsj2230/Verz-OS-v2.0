"""The model server's own program: a supervisor that loads one part at a time and gives it back.

**This is a second program in the same repository and it imports nothing from `brain`.** It runs in
an image of its own (`modelserver/Dockerfile`) beside the application, which holds neither a model
nor a machine-learning library, and the image carries this package and the libraries of the parts an
install chose and nothing of the application. Every name it shares with the application (the paths a
request is posted to, the keys of the answer, the part names, the environment variables) is spelled
here and held equal to the application's spelling by `tests/unit/test_inference_server.py`, because
two programs built apart and deployed apart that disagree about a key fail as a measurement never
recorded or a request that is a 404, and neither has a symptom.

**The shape, and what was rejected.** One container, one supervisor, and each part run as a child
process that is ended when it has been idle (`supervisor`). `brain.ops.model_server` argues the
design: one part is resident at a time so the limit is the largest and not the sum, and ending the
part's process is the only way to return its memory to the kernel for certain. Rejected: loading
every part in the supervisor and unloading a model inside a Python process, which usually does not
return the memory; one container per part, which is the sum with a second runtime in each; and a
supervisor that stops and starts the container, which needs the docker socket.

**The supervisor decides nothing about a document.** It reads a body no larger than the ceiling
the install set, hands it to the part, and returns what the part answered with a `memory` block
added. A refusal it makes itself (a part not chosen, the host short of memory, busy) is a status the
application already classifies as an outage, so the work waits in its queue and is never lost.

Task ids: M7.2.1, M7.3.3
"""
