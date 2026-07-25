import sys
from pathlib import Path

# Add project root so `from podcastDownloader.util import ...` resolves
# without needing `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent))
