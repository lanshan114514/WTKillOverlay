import unittest

from wtko.parser import extract_hud_items, is_own_kill


class ListenerTests(unittest.TestCase):
    def test_extract_hud_items(self):
        payload = {
            "events": [{"id": 1, "msg": "event"}],
            "damage": [{"id": 2, "msg": "damage"}],
        }
        events, damage = extract_hud_items(payload)
        self.assertEqual(events[0]["id"], 1)
        self.assertEqual(damage[0]["id"], 2)

    def test_own_kill_english(self):
        self.assertTrue(
            is_own_kill(
                "Alex (Tank) destroyed Enemy (Tank)",
                "Alex",
                ("destroyed", "killed"),
            )
        )

    def test_victim_is_not_own_kill(self):
        self.assertFalse(
            is_own_kill(
                "Enemy (Tank) destroyed Alex (Tank)",
                "Alex",
                ("destroyed",),
            )
        )

    def test_chinese_kill(self):
        self.assertTrue(
            is_own_kill(
                "[TAG]Alex（99A）摧毁了 Enemy（M1A2）",
                "Alex",
                ("摧毁", "击毁"),
            )
        )


if __name__ == "__main__":
    unittest.main()
