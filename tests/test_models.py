import unittest

from wtko.models import AppConfig, default_config


class ModelTests(unittest.TestCase):
    def test_default_has_five_levels(self):
        config = default_config()
        self.assertEqual(set(config.levels), {"1", "2", "3", "4", "5"})

    def test_from_dict_fills_missing_fields(self):
        config = AppConfig.from_dict(
            {
                "game": {"player_name": "Alex"},
                "levels": {"1": {"title": "ONE"}},
            }
        )
        self.assertEqual(config.game.player_name, "Alex")
        self.assertEqual(config.levels["1"].title, "ONE")
        self.assertTrue(config.levels["5"].media.endswith("kill_5.png"))


if __name__ == "__main__":
    unittest.main()
