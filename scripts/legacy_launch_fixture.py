"""Synthetic upgrade fixture used only by cloud acceptance, never shipped to users."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if __name__ == '__main__':
    import container_planner
    # Emulate the health/shutdown protocol already shipped in beta.8.
    container_planner.__version__ = '1.0.0'
    from container_planner.launcher import main
    main()
