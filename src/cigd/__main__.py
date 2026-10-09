"""Allow the pipeline to be run as python -m cigd."""

import sys

from cigd.cli import main

sys.exit(main())
