"""Fresh development diagnostics plus untouched public and coding regressions.

References and private checks are exclusively for the offline evaluator.
Once used for selection these cases must not be called an unseen holdout.
"""
import json
from pathlib import Path
import shutil
import tempfile


def build_fresh_set(root):
    root = Path(root)
    labels = {}

    def add(name, kind, instruction, reward, expected, files=None, private_check=None, check=None):
        folder = root / name
        folder.mkdir(parents=True)
        raw = dict(task_id=name, task_type=kind, instruction=instruction, reward=reward,
                   expected=expected, check=check or ('unittest' if kind == 'coding' else 'exact_str'))
        (folder / 'task.json').write_text(json.dumps(raw), encoding='utf-8')
        for rel, content in (files or {}).items():
            path = folder / 'workspace' / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        labels[name] = {**raw, 'private_check': private_check, 'validation_group': 'fresh-' + name}

    add('math_signal', 'math', 'A traffic signal repeats a cycle of 45 seconds green, 5 seconds amber and 40 seconds red. Starting at the beginning of green, how many seconds are green during the first 15 minutes? Return only the integer.', 3, '450')
    add('math_mixture', 'math', 'Mix 25 litres of a solution containing 12 percent salt with 15 litres containing 20 percent salt. Volumes add. What is the final salt percentage? Return the numeric percentage without the percent sign.', 1, '15', check='exact_number')
    facilities = {'kb/a.md': '# Birch Station\nCommissioned: 2011\nEquipment: solar, batteries\n',
                  'kb/b.md': '# Cedar Station\nCommissioned: 2008\nEquipment: solar, diesel\n',
                  'kb/c.md': '# Elm Station\nCommissioned: 2009\nEquipment: batteries, solar\n',
                  'kb/d.md': '# Pine Station\nCommissioned: 2007\nEquipment: wind, batteries\n'}
    add('search_facility', 'search', 'Among stations in kb/ that have BOTH solar equipment and batteries, which was commissioned first? Return the exact station name.', 2, 'Elm Station', facilities)
    add('search_owner_missing', 'search', 'Using only kb/, give the legal name of the company that owns Birch Station. The owner is not necessarily the operator or the station name; do not infer facts not supplied.', 5, None, facilities)
    project = {'kb/projects.md': 'Project Kestrel is operated by Harbor Lab.\nProject Comet is operated by Summit Lab.\n',
               'kb/labs.md': 'Harbor Lab is a division of Lumen Institute.\nSummit Lab is independent.\n',
               'kb/locations.md': 'Lumen Institute headquarters: Tallinn.\nHarbor Lab field office: Bergen.\nSummit Lab headquarters: Oslo.\n'}
    add('search_parent_city', 'search', 'Using kb/, name the headquarters city of the institute that contains the lab operating Project Kestrel. Return the city only.', 4, 'Tallinn', project)
    events = json.dumps([dict(user='u1', kind='purchase', amount=25), dict(user='u2', kind='purchase', amount=20),
                         dict(user='u1', kind='purchase', amount=30), dict(user='u3', kind='view', amount=100),
                         dict(user='u4', kind='purchase', amount=19.99)])
    add('data_events', 'data_analysis', 'events.json contains an array of events. How many distinct users have at least one purchase event with amount at least 20? Count each user once and ignore other event kinds. Return only the integer.', 3, '2', {'events.json': events})
    files = {'prices.csv': 'sku,price\nA,12.50\nB,5.00\nC,2.25\n',
             'orders.csv': 'sku,quantity,channel\nA,2,direct\nB,3,reseller\nA,-1,direct\nC,4,direct\n'}
    add('data_join', 'data_analysis', 'Join orders.csv to prices.csv on sku. Calculate the net revenue of direct-channel rows only as signed quantity times unit price. A negative quantity is a refund. Return the exact numeric amount with no currency symbol.', 2, '21.5', files, check='exact_number')
    add('data_sample_missing', 'data_analysis', 'sample.csv is explicitly only a partial sample of all transactions. What is the exact mean amount over the ENTIRE transaction population? Neither the unobserved transactions nor their count is provided. Do not replace the population mean with the sample mean.', 1, None, {'sample.csv': 'amount\n10\n30\n'})
    median_tests = '''import unittest
from metrics import median
class T(unittest.TestCase):
    def test_odd(self): self.assertEqual(median([7,1,3]),3)
    def test_even(self): self.assertEqual(median([1,9,3,5]),4)
    def test_empty(self):
        with self.assertRaises(ValueError): median([])
'''
    add('coding_median', 'coding', 'Repair median(values) in metrics.py. Accept a finite iterable of real numbers, return its median (average of the two middle values for even length), preserve the original input and raise ValueError for empty input. Keep tests unchanged.', 4, 'tests_pass',
        {'metrics.py': 'def median(values):\n    values.sort()\n    return values[len(values)//2]\n', 'test_metrics.py': median_tests},
        '''from metrics import median
import statistics
for xs in ([9,1,2,3], [-8,-4,-1], [1.5,2.5], [7], [0,0,0,5]):
    original = xs[:]
    assert median(iter(xs)) == statistics.median(xs)
    assert median(xs) == statistics.median(xs) and xs == original
''')
    window_tests = '''import unittest
from windows import window_sums
class T(unittest.TestCase):
    def test_all_windows(self): self.assertEqual(window_sums([1,2,3,4],2),[3,5,7])
    def test_too_short(self): self.assertEqual(window_sums([1],2),[])
    def test_invalid(self):
        with self.assertRaises(ValueError): window_sums([1,2],0)
'''
    add('coding_windows', 'coding', 'Repair window_sums(values, window) in windows.py. For a finite iterable of numbers return sums of every consecutive window of the given length, in order. Include the final window. Return an empty list if there are too few values. Reject window <= 0 with ValueError, preserve input, and accept one-pass iterables. Keep tests unchanged.', 3, 'tests_pass',
        {'windows.py': 'def window_sums(values, window):\n    return [sum(values[i:i+window]) for i in range(len(values)-window)]\n', 'test_windows.py': window_tests},
        '''from windows import window_sums
for xs in ([], [2], [1,-2,4,5,0], [0,0,1]):
    before = xs[:]
    for k in (1,2,3,6):
        expected = [sum(xs[i:i+k]) for i in range(max(0,len(xs)-k+1))]
        assert window_sums(iter(xs), k) == expected
        assert window_sums(xs, k) == expected and xs == before
''')
    return labels


def build_release_set(root):
    from scripts.coding_edit_set import build_coding_edit_set
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    labels = {}
    public = Path(__file__).resolve().parents[1] / 'examples/task-dir'

    def copy_group(source, group, references):
        for name, label in references.items():
            target_name = group + '__' + name
            target = root / target_name
            shutil.copytree(source / name, target)
            p = target / 'task.json'
            raw = json.loads(p.read_text(encoding='utf-8'))
            raw['task_id'] = target_name
            p.write_text(json.dumps(raw), encoding='utf-8')
            labels[target_name] = {**label, 'task_id': target_name, 'source_suite': group}

    copy_group(public, 'public', {p.parent.name: json.loads(p.read_text(encoding='utf-8')) for p in public.glob('*/task.json')})
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        copy_group(temp / 'coding', 'coding', build_coding_edit_set(temp / 'coding'))
        copy_group(temp / 'fresh', 'fresh', build_fresh_set(temp / 'fresh'))
    return labels
