from pathlib import Path
import json
import tempfile
import unittest

from scripts.evaluate_examples import check_answer
from scripts.validation_set import build_validation_set


class ValidationSuiteTests(unittest.TestCase):
    def test_composition_and_private_checks_are_not_in_task_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            labels = build_validation_set(Path(temp))
            self.assertEqual(len(labels), 10)
            self.assertEqual(sum(t['expected'] is None for t in labels.values()), 2)
            self.assertEqual(set(t['task_type'] for t in labels.values()), {'math', 'search', 'data_analysis', 'coding'})
            for path in Path(temp).glob('*/task.json'):
                self.assertNotIn('private_check', json.loads(path.read_text()))

    def test_hidden_check_rejects_a_fix_that_only_passes_visible_tests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); labels = build_validation_set(root)
            folder = root / 'coding_normalize'
            (folder / 'answer.txt').write_text('DONE')
            (folder / 'workspace/text_utils.py').write_text(
                "def normalize(text):\n    return ' '.join(text.split()).lower().encode('ascii','ignore').decode()\n")
            self.assertFalse(check_answer(folder, labels['coding_normalize']))

    def test_correct_normalization_passes_extra_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); labels = build_validation_set(root)
            folder = root / 'coding_normalize'
            (folder / 'answer.txt').write_text('DONE')
            (folder / 'workspace/text_utils.py').write_text("def normalize(text):\n    return ' '.join(text.split()).lower()\n")
            self.assertTrue(check_answer(folder, labels['coding_normalize']))

    def test_decimal_representation_and_invalid_number(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); labels = build_validation_set(root)
            folder = root / 'data_revenue'
            for answer, accepted in [('72.0', True), ('NaN', False), ('72 dollars', False)]:
                (folder / 'answer.txt').write_text(answer)
                self.assertEqual(check_answer(folder, labels['data_revenue']), accepted)

    def test_no_answer_on_missing_data_does_not_earn_reward(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); labels = build_validation_set(root)
            self.assertFalse(check_answer(root / 'search_missing', labels['search_missing']))


if __name__ == '__main__':
    unittest.main()
