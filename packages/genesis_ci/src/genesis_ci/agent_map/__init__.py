"""The map workflow for a repository no analyzer reads.

The coding agent finds the entry points, describes the flows and reads the changes
itself. The CLI freezes the source, confirms every citation against it, places the
changed lines on the steps that cite them, and writes the same map and change report
as the Python workflow.

This package stands apart from that workflow: it imports the contracts, the snapshot
and the shared session and loop helpers, and nothing of the Python analysis.
"""

from .session import prepare
from .workspace import Workspace

__all__ = ["Workspace", "prepare"]
