"""Compatibility entry point: the former bug probes are now regression tests."""
import unittest
import test_admin_fixes

if __name__=='__main__':
    unittest.main(module=test_admin_fixes,verbosity=2)
