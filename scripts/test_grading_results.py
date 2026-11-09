"""Typed result comparison independent of PostgreSQL and preview rendering."""
from pathlib import Path
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grading_results import canonical, compare_complete, policy_from, column_mapping, GradingLimitError


class ResultTests(unittest.TestCase):
    def test_ordered_tolerance_permutations_keep_duplicate_counts(self):
        p=policy_from({'numeric_absolute_tolerance':'0.01'})
        ref=[(1,'A',Decimal('2')),(1,'B',Decimal('1'))]
        swapped=[(1,'B',Decimal('1.001')),(1,'A',Decimal('2.001'))]
        self.assertTrue(compare_complete(ref,swapped,p,True,order_keys=[0])[0])
        self.assertFalse(compare_complete(ref,[swapped[0],swapped[0]],p,True,order_keys=[0])[0])

    def test_large_ordered_tolerance_does_not_need_bag_matching(self):
        p=policy_from({'numeric_absolute_tolerance':'0.01'})
        ref=[(n,Decimal(n)) for n in range(1001)]
        actual=[(n,Decimal(n)+Decimal('0.001')) for n in range(1001)]
        self.assertTrue(compare_complete(ref,actual,p,True,order_keys=[0])[0])
        actual[0],actual[1]=actual[1],actual[0]
        with self.assertRaises(GradingLimitError):
            compare_complete(ref,actual,p,True,order_keys=[0])
    def test_order_ties_can_swap_but_other_groups_cannot(self):
        reference=[(8,'A',300),(9,'NEW',264),(9,'DRAMA',264),(10,'B',100)]
        swapped=[reference[0],reference[2],reference[1],reference[3]]
        self.assertEqual(compare_complete(reference,swapped,policy_from({}),True,order_keys=[0,2])[:2],(True,'correct'))
        self.assertEqual(compare_complete(reference,list(reversed(reference)),policy_from({}),True,order_keys=[0,2])[:2],(False,'wrong_order'))
        changed=[reference[0],(9,'DRAMA',265),reference[1],reference[3]]
        self.assertEqual(compare_complete(reference,changed,policy_from({}),True,order_keys=[0,2])[:2],(False,'wrong_data'))
    def compare(self, a, b, ordered=False, **policy):
        return compare_complete(a, b, policy_from(policy), ordered)[:2]

    def test_text_is_exact_and_typed(self):
        for a, b in [('001', '1'), ('A', 'a'), ('x ', 'x'), ('1', 1), (True, 1), (None, '')]:
            with self.subTest(a=a, b=b):
                self.assertNotEqual(canonical(a), canonical(b))

    def test_decimal_precision_and_numeric_equivalence(self):
        self.assertEqual(canonical(1), canonical(Decimal('1.000')))
        self.assertNotEqual(canonical(Decimal('1.000000000000000000000000000001')),
                            canonical(Decimal('1.000000000000000000000000000002')))

    def test_duplicate_multiplicity(self):
        self.assertEqual(self.compare([(1,), (1,), (2,)], [(2,), (1,), (1,)]), (True, 'correct'))
        self.assertEqual(self.compare([(1,), (1,), (2,)], [(2,), (2,), (1,)]), (False, 'wrong_data'))

    def test_order_and_count(self):
        self.assertEqual(self.compare([(1,), (2,)], [(2,), (1,)], True), (False, 'wrong_order'))
        self.assertEqual(self.compare([(1,)], [(1,), (1,)]), (False, 'row_count_mismatch'))

    def test_full_results_after_preview_boundary(self):
        a = [(n,) for n in range(1000)]
        b = a.copy()
        b[900] = (-1,)
        self.assertEqual(self.compare(a, b), (False, 'wrong_data'))

    def test_explicit_numeric_tolerance_and_matching(self):
        self.assertFalse(self.compare([(Decimal('1.01'),)], [(1,)])[0])
        self.assertTrue(self.compare([(Decimal('1.01'),)], [(1,)], numeric_absolute_tolerance='0.02')[0])
        # A greedy match can fail: 0.1 must match 0.0 so 0.2 can match 0.3.
        self.assertTrue(self.compare([(Decimal('.1'),), (Decimal('.2'),)], [(Decimal('.3'),), (Decimal('0'),)],
                                     numeric_absolute_tolerance='.15')[0])
        self.assertFalse(self.compare([('001',)], [('1',)], numeric_absolute_tolerance='100')[0])

    def test_column_policy(self):
        self.assertIsNone(column_mapping(['a', 'b'], ['b', 'a'], [23, 25], [25, 23], policy_from()))
        self.assertEqual(column_mapping(['a', 'b'], ['b', 'a'], [23, 25], [25, 23], policy_from({'column_order': False})), [1, 0])
        self.assertIsNone(column_mapping(['a'], ['a'], [23], [25], policy_from()))

    def test_resource_limit_raises_instead_of_accepting_preview(self):
        with patch('grading_results.MAX_GRADE_ROWS', 2), self.assertRaises(GradingLimitError):
            self.compare([(1,)] * 3, [(1,)] * 3)

    def test_invalid_policies_rejected(self):
        for policy in [{'unknown': True}, {'numeric_absolute_tolerance': '-1'}, {'numeric_relative_tolerance': 'NaN'}]:
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                policy_from(policy)


if __name__ == '__main__':
    unittest.main(verbosity=2)
