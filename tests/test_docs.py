import unittest

from feiyue.docs import sort_applications_by_result


class SortApplicationsByResultTest(unittest.TestCase):
    def test_groups_known_results_and_keeps_group_order_stable(self):
        links = [
            {"row_id": "admit-1"},
            {"row_id": "reject"},
            {"row_id": "chosen"},
            {"row_id": "admit-2"},
            {"row_id": "blank"},
            {"row_id": "waitlist"},
            {"row_id": "unknown"},
        ]
        applications = {
            "admit-1": {"result": "Admit"},
            "reject": {"result": "Reject"},
            "chosen": {"result": "Chosen"},
            "admit-2": {"result": "Admit"},
            "blank": {"result": None},
            "waitlist": {"result": "Waitlist"},
            "unknown": {"result": "Pending"},
        }

        ordered = sort_applications_by_result(links, applications)

        self.assertEqual(
            [link["row_id"] for link in ordered],
            [
                "chosen",
                "admit-1",
                "admit-2",
                "waitlist",
                "reject",
                "blank",
                "unknown",
            ],
        )

    def test_does_not_mutate_the_seatable_link_list(self):
        links = [{"row_id": "reject"}, {"row_id": "chosen"}]
        applications = {
            "reject": {"result": "Reject"},
            "chosen": {"result": "Chosen"},
        }

        ordered = sort_applications_by_result(links, applications)

        self.assertEqual(
            [link["row_id"] for link in ordered], ["chosen", "reject"]
        )
        self.assertEqual(
            [link["row_id"] for link in links], ["reject", "chosen"]
        )


if __name__ == "__main__":
    unittest.main()
