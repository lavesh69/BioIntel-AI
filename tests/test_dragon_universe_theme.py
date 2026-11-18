import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest
from biointel.ui.dragon_universe import (
    DRAGON_PALETTE,
    apply_dragon_universe_theme,
    render_dragon_universe,
    render_dragon_theme_settings_sidebar,
)
from biointel.ui.dragon_universe.theme_manager import generate_dragon_universe_css

class TestDragonUniverseTheme(unittest.TestCase):
    def test_dragon_palette_and_css(self):
        self.assertIn("electric_cyan", DRAGON_PALETTE)
        self.assertEqual(DRAGON_PALETTE["electric_cyan"], "#00D9FF")
        css = generate_dragon_universe_css()
        self.assertIn("bio-dragon-divider", css)
        self.assertIn("glassmorphism", css.lower())

if __name__ == "__main__":
    unittest.main()
