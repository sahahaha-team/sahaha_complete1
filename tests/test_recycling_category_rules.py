import unittest
from chatbot.answer_goal import answer_goal
from chatbot.structured_answers import explicit_table_answer


class CategoryRuleTests(unittest.TestCase):
    def setUp(self):
        self.units = [
            '쓰레기 종류 — 수: 재활용품(종이류(박스 등), 폐형광등, 폐건전지), 일반쓰레기(불연성), 소형폐가전',
            '일반쓰레기는 종량제봉투에 넣습니다. 재활용품은 종량제봉투에 담지 않으며, 반드시 품목별로 분리하여 배출하여야 합니다.',
        ]

    def test_conditional_permission_is_not_service_overview(self):
        for q in ('형광등을 봉투에 넣으면 되나요?', '형광등을 봉투에 넣어도 되나요?',
                  '형광등을 봉투에 버리면 돼요?'):
            self.assertEqual(answer_goal(q), 'conditions')

    def test_explicit_category_membership_connects_to_own_rule(self):
        answer = explicit_table_answer('형광등을 종량제봉투에 넣으면 되나요?', self.units, '배출요령')
        self.assertIn('폐형광등', answer)
        self.assertIn('종량제봉투에 담지 않으며', answer)
        self.assertIn('품목별로 분리', answer)

    def test_adjacent_category_cannot_inherit_rule(self):
        self.assertIsNone(explicit_table_answer('소형폐가전을 봉투에 넣으면 되나요?', self.units, '배출요령'))

    def test_two_items_from_different_categories_cannot_share_rule(self):
        self.assertIsNone(explicit_table_answer('형광등과 소형폐가전을 봉투에 넣으면 되나요?', self.units, '배출요령'))

    def test_unlisted_item_or_unconfirmed_damage_cannot_inherit_rule(self):
        for q in ('LED전구를 봉투에 넣으면 되나요?', '깨진 형광등을 봉투에 넣으면 되나요?'):
            self.assertIsNone(explicit_table_answer(q, self.units, '배출요령'))


if __name__ == '__main__':
    unittest.main()
