"""
test_parsers.py — Unit tests for Python, Java, and C# parsers.
"""

import sys
import os
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from parsers import python_parser, java_parser, csharp_parser


PYTHON_SOURCE = '''
class MyService:
    def __init__(self):
        self.data = []

    def process(self, item):
        if item:
            return item
        return None

    def _helper(self):
        pass

class SimpleUtil:
    def add(self, a, b):
        return a + b
'''

JAVA_SOURCE = '''
import com.example.UserRepository;
import java.util.List;

public class OrderService {
    private UserRepository repo;

    public OrderService(UserRepository repo) {
        this.repo = repo;
    }

    public String processOrder(String orderId) {
        if (orderId == null) {
            throw new IllegalArgumentException("orderId cannot be null");
        }
        return "processed:" + orderId;
    }
}
'''

CSHARP_SOURCE = '''
using System;
using System.Collections.Generic;

namespace App.Services
{
    public class InventoryService
    {
        private readonly List<string> _items = new();

        public void AddItem(string name)
        {
            if (string.IsNullOrEmpty(name))
                throw new ArgumentException("name is required");
            _items.Add(name);
        }

        public int GetCount()
        {
            return _items.Count;
        }
    }
}
'''


def _write_temp(content: str, suffix: str) -> str:
    fh = tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8')
    fh.write(content)
    fh.close()
    return fh.name


class TestPythonParser(unittest.TestCase):
    def setUp(self):
        self.path = _write_temp(PYTHON_SOURCE, '.py')

    def tearDown(self):
        os.unlink(self.path)

    def test_finds_two_classes(self):
        result = python_parser.parse(self.path)
        self.assertEqual(len(result), 2)

    def test_class_names(self):
        names = {c['name'] for c in python_parser.parse(self.path)}
        self.assertIn('MyService', names)
        self.assertIn('SimpleUtil', names)

    def test_methods_extracted(self):
        result = python_parser.parse(self.path)
        svc = next(c for c in result if c['name'] == 'MyService')
        self.assertIn('process', svc['methods'])

    def test_cc_positive(self):
        for cls in python_parser.parse(self.path):
            self.assertGreater(cls['cyclomatic_complexity'], 0)

    def test_has_public_api(self):
        result = python_parser.parse(self.path)
        svc = next(c for c in result if c['name'] == 'MyService')
        self.assertTrue(svc['has_public_api'])

    def test_required_keys(self):
        result = python_parser.parse(self.path)
        required = {'name','line_start','line_end','methods','cyclomatic_complexity','fan_in','fan_out','rpn','risk_level'}
        for cls in result:
            for k in required:
                self.assertIn(k, cls)

    def test_empty_file(self):
        p = _write_temp('', '.py')
        try:
            result = python_parser.parse(p)
            self.assertIsInstance(result, list)
        finally:
            os.unlink(p)


class TestJavaParser(unittest.TestCase):
    def setUp(self):
        self.path = _write_temp(JAVA_SOURCE, '.java')

    def tearDown(self):
        os.unlink(self.path)

    def test_finds_class(self):
        result = java_parser.parse(self.path)
        self.assertGreater(len(result), 0)

    def test_class_name(self):
        names = {c['name'] for c in java_parser.parse(self.path)}
        self.assertIn('OrderService', names)

    def test_methods_extracted(self):
        result = java_parser.parse(self.path)
        svc = next(c for c in result if c['name'] == 'OrderService')
        self.assertIn('processOrder', svc['methods'])

    def test_cc_positive(self):
        for cls in java_parser.parse(self.path):
            self.assertGreater(cls['cyclomatic_complexity'], 0)


class TestCSharpParser(unittest.TestCase):
    def setUp(self):
        self.path = _write_temp(CSHARP_SOURCE, '.cs')

    def tearDown(self):
        os.unlink(self.path)

    def test_finds_class(self):
        result = csharp_parser.parse(self.path)
        self.assertGreater(len(result), 0)

    def test_class_name(self):
        names = {c['name'] for c in csharp_parser.parse(self.path)}
        self.assertIn('InventoryService', names)

    def test_methods_extracted(self):
        result = csharp_parser.parse(self.path)
        svc = next(c for c in result if c['name'] == 'InventoryService')
        self.assertTrue(len(svc['methods']) > 0)

    def test_public_api_detected(self):
        result = csharp_parser.parse(self.path)
        svc = next(c for c in result if c['name'] == 'InventoryService')
        self.assertTrue(svc['has_public_api'])


if __name__ == "__main__":
    unittest.main()
